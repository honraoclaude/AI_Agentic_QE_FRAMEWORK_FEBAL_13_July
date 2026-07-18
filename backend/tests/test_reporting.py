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
