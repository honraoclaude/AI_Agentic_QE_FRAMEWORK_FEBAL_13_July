"""Stakeholder reporting: releases, sealed MI packs, flow/quality/worklist."""

from sqlalchemy import select

from app.models import AuditEvent, Release, ReportSnapshot, Story
from app.services import reporting, workflow
from app.services.jira import sync_service
from app.util import canonical_json, sha256_hex


async def _seed(session, adapter) -> list[Story]:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return list(
        (await session.execute(select(Story).order_by(Story.jira_key))).scalars()
    )


async def _run_one(session, story, agent_key="story_quality"):
    run = await workflow.latest_run(session, story.id, agent_key)
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    await workflow.accept_run(session, run.id, actor="Test Lead")
    return run


async def test_exec_mi_pack_shape_and_metrics(session, adapter):
    stories = await _seed(session, adapter)
    await _run_one(session, stories[0])
    release = Release(name="Release 26.8", target_date="2026-08-28",
                      story_ids=[s.id for s in stories[:2]])
    session.add(release)
    await session.flush()

    pack = await reporting.exec_mi_pack(session, release)
    assert pack["release"]["name"] == "Release 26.8"
    assert pack["release"]["stories"] == 2
    assert len(pack["stories"]) == 2
    assert pack["confidence_index"] is not None  # at least one assessed story
    assert set(pack["bands"]) == {"HEALTHY", "AT_RISK", "CRITICAL", "BLOCKED", "NO_DATA"}
    # The WARN acceptance created quality debt — visible in the MI position.
    assert pack["quality_debt"]["open"] >= 1
    ai = pack["ai_governance"]
    assert ai["runs_executed"] >= 1 and ai["human_decided_pct"] == 1.0
    assert ai["first_time_right_rate"] == 1.0
    # Honest labelling: rework, not change-failure-rate.
    assert "rework_story_rate" in pack["flow"]


async def test_seal_creates_immutable_hashed_snapshot(session, adapter):
    stories = await _seed(session, adapter)
    await _run_one(session, stories[0])
    release = Release(name="Release 26.9", story_ids=[stories[0].id])
    session.add(release)
    await session.flush()

    meta = await reporting.seal_mi_pack(session, release, actor="CTO")
    snap = await session.get(ReportSnapshot, meta["snapshot_id"])
    # The hash is canonical over the stored payload — recomputable forever.
    assert sha256_hex(canonical_json(snap.payload)) == snap.payload_hash
    assert meta["payload_hash"] == snap.payload_hash
    # Sealing entered the audit chain.
    ev = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.event_type == "REPORT_SEALED")
        )
    ).scalars().all()
    assert len(ev) == 1 and ev[0].payload["payload_hash"] == snap.payload_hash
    # Sealing twice produces a second, distinct snapshot (never mutation).
    meta2 = await reporting.seal_mi_pack(session, release, actor="CTO")
    assert meta2["snapshot_id"] != meta["snapshot_id"]
    # Render works for the sealed pack.
    html = reporting.render_mi_html(snap.payload, snap.payload_hash)
    assert "Release 26.9" in html and snap.payload_hash in html


async def test_flow_report_queue_and_blocking_questions(session, adapter):
    stories = await _seed(session, adapter)
    s = stories[0]
    # story_quality accepted -> three_amigos? No: chain order. Accept the
    # first agent so the second is AWAITING_APPROVAL (queue depth >= 1).
    await _run_one(session, s)
    flow = await reporting.flow_report(session)
    assert flow["hitl_queue"]["depth"] >= 1
    assert any(r["kind"] == "RUN_APPROVAL" for r in flow["hitl_queue"]["runs"])
    # Run three_amigos to surface its blocking question in the aging list.
    for key in ("fca_regulatory_impact", "consumer_duty_mapper",
                "compliance_ac_advisor", "three_amigos"):
        await _run_one(session, s, key)
    flow = await reporting.flow_report(session)
    assert any("Q2" in q["question"] or "tolerance" in q["question"].lower()
               for q in flow["blocking_questions"])


async def test_quality_report_and_worklist(session, adapter):
    stories = await _seed(session, adapter)
    s = stories[0]
    await _run_one(session, s)  # story_quality WARN -> findings exist
    quality = await reporting.quality_report(session)
    assert "first_time_right" in quality and "flake_index" in quality
    assert quality["first_time_right"][0]["first_time_right_rate"] == 1.0

    wl = await reporting.worklist(session, s.id)
    assert wl["items"], "accepted WARN run should produce worklist findings"
    # Strongest first.
    from app.services.agents.output_schemas import severity_rank

    ranks = [severity_rank(i["severity"]) for i in wl["items"]]
    assert ranks == sorted(ranks, reverse=True)


async def test_portfolio_trend_insufficient_then_direction(session, adapter):
    stories = await _seed(session, adapter)
    await _run_one(session, stories[0])

    release_a = Release(name="Release A", story_ids=[s.id for s in stories[:2]])
    session.add(release_a)
    await session.flush()
    await reporting.seal_mi_pack(session, release_a, actor="CTO")

    # One sealed release is not enough to call a direction.
    trend = await reporting.portfolio_trend(session)
    assert trend["summary"]["sealed_releases"] == 1
    assert trend["summary"]["sufficient_for_trend"] is False
    assert trend["trend"]["confidence_index"] == "INSUFFICIENT_DATA"

    # A second sealed release makes a direction computable (not asserting
    # which way — the fixture data doesn't guarantee movement — just shape).
    release_b = Release(name="Release B", story_ids=[s.id for s in stories[:2]])
    session.add(release_b)
    await session.flush()
    await reporting.seal_mi_pack(session, release_b, actor="CTO")

    trend = await reporting.portfolio_trend(session)
    assert trend["summary"]["sealed_releases"] == 2
    assert trend["summary"]["sufficient_for_trend"] is True
    assert trend["trend"]["confidence_index"] in ("IMPROVING", "DEGRADING", "FLAT")
    assert [p["release_name"] for p in trend["points"]] == ["Release A", "Release B"]


async def test_sla_breach_report_flags_over_threshold(session, adapter):
    stories = await _seed(session, adapter)
    s = stories[0]
    await _run_one(session, s)  # leaves the next agent AWAITING_APPROVAL

    # A threshold below zero guarantees a breach regardless of elapsed time.
    forced = await reporting.sla_breach_report(session, {"REFINEMENT": -1})
    assert forced["summary"]["total"] >= 1
    assert any(b["phase"] == "REFINEMENT" for b in forced["breaches"])
    assert forced["thresholds"]["REFINEMENT"] == -1
    assert all(b["over_by_days"] >= 0 for b in forced["breaches"])

    # Unconfigured phases fall back to the module defaults.
    default = await reporting.sla_breach_report(session)
    assert default["thresholds"]["RELEASE"] == reporting.DEFAULT_SLA_DAYS["RELEASE"]
    # A generous threshold clears the queue.
    clear = await reporting.sla_breach_report(session, {"REFINEMENT": 999})
    assert not any(b["phase"] == "REFINEMENT" for b in clear["breaches"])


async def test_readiness_report_scope_risk_and_sort(session, adapter):
    stories = await _seed(session, adapter)
    at_risk, healthy = stories[0], stories[1]
    release = Release(
        name="Release RD", target_date="2099-01-01",
        story_ids=[at_risk.id, healthy.id],
    )
    session.add(release)
    await session.flush()
    # Accepting a WARN verdict opens a risk-register entry (same as the exec
    # MI test) — that's what should push this story's scope_risk up.
    await _run_one(session, at_risk)

    report = await reporting.readiness_report(session)
    assert report["summary"]["total"] == len(stories)
    row = next(r for r in report["stories"] if r["jira_key"] == at_risk.jira_key)
    assert row["target_date"] == "2099-01-01"
    assert row["days_to_target"] is not None and row["days_to_target"] > 0
    assert row["open_risks"] >= 1
    assert row["scope_risk"] in ("MEDIUM", "HIGH")
    # HIGH/MEDIUM risk stories sort before untouched LOW-risk ones.
    risk_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    ranks = [risk_rank[r["scope_risk"]] for r in report["stories"]]
    assert ranks == sorted(ranks)


async def test_ac_ambiguity_digest_surfaces_blocking_questions(session, adapter):
    stories = await _seed(session, adapter)
    s = stories[0]
    await _run_one(session, s)  # story_quality, upstream of the regulatory chain
    for key in ("fca_regulatory_impact", "consumer_duty_mapper",
                "compliance_ac_advisor", "three_amigos"):
        await _run_one(session, s, key)

    digest = await reporting.ac_ambiguity_digest(session)
    assert digest["summary"]["stories_with_open_questions"] >= 1
    row = next(r for r in digest["stories"] if r["jira_key"] == s.jira_key)
    assert row["blocking"], "three_amigos demo output should include a blocking question"


async def test_override_digest_groups_rejections_and_guidance(session, adapter):
    stories = await _seed(session, adapter)
    s = stories[0]
    run = await workflow.latest_run(session, s.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    await workflow.reject_run(
        session, run.id, actor="Test Lead", reason="Missing AC for refunds"
    )

    digest = await reporting.override_digest(session)
    assert digest["summary"]["total_overrides"] >= 1
    row = next(a for a in digest["agents"] if a["agent_key"] == "story_quality")
    assert any(
        i["kind"] == "REJECTED" and "refunds" in i["reason"].lower()
        for i in row["items"]
    )

    scoped = await reporting.override_digest(session, assignee=s.assignee)
    if s.assignee:
        assert scoped["summary"]["total_overrides"] >= 1
    else:
        assert scoped["summary"]["total_overrides"] == 0
