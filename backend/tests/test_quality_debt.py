"""Risk Acceptance Register (quality-debt ledger) + Flaky-Test Intelligence."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models import Gate, GateStatus, Phase, RiskAcceptance, Story
from app.services import challenger, flaky_intel, risk_register, workflow
from app.services.agents.demo_outputs import build
from app.services.jira import sync_service
from app.util import utcnow


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


async def _accepted_warn_run(session, adapter, reason=""):
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    run = await workflow.accept_run(session, run.id, "QE Lead", reason)
    return story, run


# ------------------------------------------------------------ risk register


async def test_accepting_a_warn_run_registers_the_risk(session, adapter):
    story, run = await _accepted_warn_run(
        session, adapter, reason="Fix scheduled for Sprint 14"
    )
    assert (run.output_json or {}).get("verdict") == "WARN"  # demo premise

    register = await risk_register.list_register(session, story.id)
    entries = register["entries"]
    assert len(entries) >= 1
    e = next(x for x in entries if x["source"] == "RUN_ACCEPTED_WITH_FINDINGS")
    assert e["accepted_by"] == "QE Lead"
    assert e["rationale"] == "Fix scheduled for Sprint 14"  # Decision A flows in
    assert e["status"] == "OPEN" and not e["overdue"]
    assert e["review_by"] is not None
    assert register["summary"]["open"] >= 1


async def test_sweep_is_idempotent(session, adapter):
    story, _ = await _accepted_warn_run(session, adapter)
    before = (await risk_register.list_register(session, story.id))["summary"]["total"]
    assert await risk_register.sweep(session, story.id) == 0  # no duplicates
    after = (await risk_register.list_register(session, story.id))["summary"]["total"]
    assert after == before


async def test_review_restarts_window_and_close_ends_it(session, adapter):
    story, _ = await _accepted_warn_run(session, adapter)
    entry = (await risk_register.list_register(session, story.id))["entries"][0]

    reviewed = await risk_register.review(session, entry["id"], "QE Lead", "still fine")
    assert reviewed["status"] == "REVIEWED" and reviewed["reviewed_by"] == "QE Lead"
    assert reviewed["review_by"] > entry["review_by"]  # window restarted

    closed = await risk_register.close(session, entry["id"], "QE Lead", "fixed in 1.2")
    assert closed["status"] == "CLOSED"
    with pytest.raises(risk_register.RegisterError):
        await risk_register.review(session, entry["id"], "QE Lead", "…")


async def test_overdue_flag(session, adapter):
    story, _ = await _accepted_warn_run(session, adapter)
    row = (
        await session.execute(select(RiskAcceptance))
    ).scalars().first()
    row.review_by = utcnow() - timedelta(days=1)
    await session.flush()
    entry = (await risk_register.list_register(session, story.id))["entries"][0]
    assert entry["overdue"] is True
    assert (await risk_register.list_register(session, story.id))["summary"]["overdue"] == 1


async def test_gate_signed_over_warn_registers(session, adapter):
    story, _ = await _accepted_warn_run(session, adapter)
    gate = (
        await session.execute(select(Gate).where(
            Gate.story_id == story.id, Gate.phase == Phase.REFINEMENT
        ))
    ).scalar_one()
    gate.status = GateStatus.SIGNED_OFF
    gate.approver_name, gate.approver_role = "PO", "Product Owner"
    gate.rationale = "Ship it — WARNs understood"
    gate.decided_at = utcnow()
    await session.flush()
    await risk_register.sweep(session, story.id)
    register = await risk_register.list_register(session, story.id)
    gate_entries = [e for e in register["entries"] if e["source"] == "GATE_SIGNED_OVER_WARN"]
    assert len(gate_entries) == 1
    assert gate_entries[0]["accepted_by"] == "PO"
    assert gate_entries[0]["rationale"] == "Ship it — WARNs understood"


async def test_challenger_surfaces_open_register_entries(session, adapter):
    story, _ = await _accepted_warn_run(session, adapter)
    result = await challenger.challenges_for_gate(session, story.id, Phase.REFINEMENT)
    kinds = [c["kind"] for c in result["challenges"]]
    assert kinds and kinds[0] == "OPEN_ACCEPTED_RISKS"  # strongest-first


# ------------------------------------------------------ flaky intelligence


def test_signature_is_stable_across_volatile_parts():
    a = flaky_intel.signature_of(
        "HouseholdRollupTest.testBulk",
        "Timeout after 30000ms waiting for id 003Ab000012XyZ on 2026-07-18",
    )
    b = flaky_intel.signature_of(
        "HouseholdRollupTest.testBulk",
        "Timeout after 45123ms waiting for id 003Ab999999QqQ on 2026-07-19",
    )
    c = flaky_intel.signature_of("OtherTest", "Timeout after 30000ms")
    assert a == b and a != c


def _analyst_run(run_id: str, failures: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id, agent_key="test_execution_analyst",
        output_json={"failures": failures},
    )


async def test_ledger_accumulates_across_runs_idempotently(session, adapter):
    await _seed(session, adapter)
    f = {"test_name": "t1", "detail": "Timeout after 30000ms", "likely_flaky": True}
    r1 = _analyst_run("run-1", [f])
    assert await flaky_intel.record_from_run(session, r1, "WLTH-101") == 1
    assert await flaky_intel.record_from_run(session, r1, "WLTH-101") == 0  # same run
    r2 = _analyst_run("run-2", [dict(f, detail="Timeout after 91ms")])
    assert await flaky_intel.record_from_run(session, r2, "WLTH-102") == 1

    ledger = await flaky_intel.ledger(session)
    sig = ledger["signatures"][0]
    assert sig["occurrences"] == 2 and sig["flaky_votes"] == 2
    assert set(sig["stories_seen"]) == {"WLTH-101", "WLTH-102"}
    assert sig["flake_score"] >= 25  # recurrent + analyst-flagged


async def test_quarantine_requires_owner_and_expiry(session, adapter):
    await _seed(session, adapter)
    await flaky_intel.record_from_run(
        session, _analyst_run("run-1", [{"test_name": "t", "detail": "x", "likely_flaky": False}]),
        "WLTH-101",
    )
    sig_id = (await flaky_intel.ledger(session))["signatures"][0]["id"]
    with pytest.raises(flaky_intel.FlakyError):
        await flaky_intel.quarantine(session, sig_id, "QE", owner="", expiry_days=30, note="")
    with pytest.raises(flaky_intel.FlakyError):
        await flaky_intel.quarantine(session, sig_id, "QE", owner="Sam", expiry_days=0, note="")
    q = await flaky_intel.quarantine(session, sig_id, "QE", owner="Sam", expiry_days=14, note="n")
    assert q["status"] == "QUARANTINED" and q["owner"] == "Sam"
    assert q["quarantine_expiry"] is not None


async def test_feed_includes_quarantined_and_scored_only(session, adapter):
    await _seed(session, adapter)
    # Low-score signature: seen once, not analyst-flagged -> not fed.
    await flaky_intel.record_from_run(
        session, _analyst_run("r1", [{"test_name": "low", "detail": "x", "likely_flaky": False}]),
        "WLTH-101",
    )
    # Recurrent flaky signature -> fed.
    for i in range(2):
        await flaky_intel.record_from_run(
            session, _analyst_run(f"h{i}", [{"test_name": "hot", "detail": "Timeout 1ms", "likely_flaky": True}]),
            "WLTH-101",
        )
    fed = {k["test_name"] for k in await flaky_intel.known_signatures(session)}
    assert "hot" in fed and "low" not in fed


async def test_demo_analyst_annotates_known_flakes(session, adapter):
    story = await _seed(session, adapter)
    junit = {
        "kind": "JUNIT", "filename": "r.xml", "summary": "s",
        "parsed": {
            "total": 3, "passed": 2, "failed": 1, "errors": 0, "skipped": 0,
            "all_tests": ["testA", "testB", "testTimeout"],
            "failures": [{"name": "testTimeout", "message": "connection timeout to sandbox"}],
        },
    }
    known = [{
        "id": "FLK-abcd1234", "test_name": "testTimeout", "status": "QUARANTINED",
        "flake_score": 70, "occurrences": 7, "stories_seen": 3, "owner": "Sam",
        "quarantine_expiry": None,
    }]
    upstream = [{"agent_key": "flaky_intel", "agent_name": "Flaky-Test Intelligence",
                 "output": {"known_flaky_signatures": known}}]
    out = build("test_execution_analyst", story, None, artifacts=[junit], upstream=upstream)
    f = next(x for x in out["failures"] if x["test_name"] == "testTimeout")
    assert f["likely_flaky"] and f["rerun_recommended"]
    assert "FLK-abcd1234" in f["detail"] and "QUARANTINED" in f["detail"]
    assert any("flaky" in fi["title"].lower() for fi in out["findings"])


async def test_demo_triage_withdraws_defect_for_known_flaky_cluster(session, adapter):
    story = await _seed(session, adapter)
    junit = {
        "kind": "JUNIT", "filename": "r.xml", "summary": "s",
        "parsed": {
            "total": 2, "passed": 1, "failed": 1, "errors": 0, "skipped": 0,
            "all_tests": ["bulkTest"],
            "failures": [{"name": "bulkTest", "message": "Too many SOQL queries: 101"}],
        },
    }
    known = [{"id": "FLK-x", "test_name": "bulkTest", "status": "WATCH",
              "flake_score": 45, "occurrences": 3, "stories_seen": 2, "owner": None,
              "quarantine_expiry": None}]
    upstream = [{"agent_key": "flaky_intel", "agent_name": "Flaky-Test Intelligence",
                 "output": {"known_flaky_signatures": known}}]

    with_feed = build("defect_triage", story, None, artifacts=[junit], upstream=upstream)
    without = build("defect_triage", story, None, artifacts=[junit], upstream=[])
    assert without["suggested_defects"]  # normally raises a defect
    assert not with_feed["suggested_defects"]  # known flake -> withdrawn
    assert with_feed["clusters"][0]["classification"] == "FLAKY"
    assert with_feed["flaky_count"] == 1
