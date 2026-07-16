import base64
import json

import pytest
from sqlalchemy import select

from app.models import AuditEvent, Phase, PushStatus, PushType, Story
from app.services import settings_service, workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import push_service, sync_service

PLATFORM = "http://localhost:5173"


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


async def _accepted_first_run(session, story):
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    await workflow.accept_run(session, run.id, actor="Test Lead")
    return run


async def test_draft_requires_accepted_run(session, adapter):
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    # Run has not even executed — drafting a summary is illegal.
    with pytest.raises(workflow.WorkflowError):
        await push_service.draft_agent_summary(session, run.id, "Test Lead", PLATFORM)


async def test_draft_approve_send_happy_path(session, adapter):
    story = await _seed(session, adapter)
    run = await _accepted_first_run(session, story)

    item = await push_service.draft_agent_summary(session, run.id, "Test Lead", PLATFORM)
    assert item.status == PushStatus.DRAFT
    # Preview shows exactly what will be posted, before anything is sent.
    assert "Story Quality Agent" in item.payload["preview_text"]
    assert adapter.posted_comments == []

    await push_service.approve_and_send(session, adapter, item.id, "Test Lead")
    await session.commit()
    assert item.status == PushStatus.SENT
    assert item.approved_by == "Test Lead"
    assert len(adapter.posted_comments) == 1
    assert adapter.posted_comments[0]["key"] == "WLTH-101"

    event_types = {
        e.event_type
        for e in (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_id == item.id)
            )
        ).scalars()
    }
    assert {"PUSH_DRAFTED", "PUSH_APPROVED", "PUSH_SENT"} <= event_types


async def test_failed_push_goes_to_retry_queue_and_recovers(session, adapter):
    story = await _seed(session, adapter)
    run = await _accepted_first_run(session, story)
    item = await push_service.draft_agent_summary(session, run.id, "Test Lead", PLATFORM)

    adapter.fail_pushes = True
    await push_service.approve_and_send(session, adapter, item.id, "Test Lead")
    assert item.status == PushStatus.FAILED
    assert item.attempts == 1
    assert "simulated Jira outage" in item.last_error

    # Approved post is never lost — retry succeeds once Jira is back.
    adapter.fail_pushes = False
    await push_service.retry(session, adapter, item.id, "Test Lead")
    assert item.status == PushStatus.SENT
    assert item.attempts == 2
    assert len(adapter.posted_comments) == 1

    event_types = [
        e.event_type
        for e in (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id == item.id)
                .order_by(AuditEvent.id)
            )
        ).scalars()
    ]
    assert event_types == [
        "PUSH_DRAFTED",
        "PUSH_APPROVED",
        "PUSH_FAILED",
        "PUSH_RETRIED",
        "PUSH_SENT",
    ]


async def _accept_phase(session, story, phase):
    for agent in agents_for_phase(phase):
        run = await workflow.latest_run(session, story.id, agent.key)
        await workflow.approve_and_run(session, run.id, approver="Test Lead")
        await workflow.accept_run(session, run.id, actor="Test Lead")


async def test_gate_signoff_auto_pushes_comment_label_and_transition(session, adapter):
    story = await _seed(session, adapter)
    await _accept_phase(session, story, Phase.REFINEMENT)
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    await workflow.signoff_gate(
        session, gate.id, "Priya Sharma", "Product Owner", "Gate 1 criteria met."
    )

    cfg = await settings_service.update_settings(
        session,
        {"gates": {"REFINEMENT": {"transition_name": "Ready for Dev"}}},
        actor="test",
    )
    items = await push_service.handle_gate_signoff(
        session, adapter, story, gate, cfg, actor="Priya Sharma"
    )
    await session.commit()

    by_type = {i.push_type: i for i in items}
    assert set(by_type) == {PushType.COMMENT, PushType.LABEL, PushType.TRANSITION}
    assert all(i.status == PushStatus.SENT for i in items)
    assert all(i.approved_by == "Priya Sharma" for i in items)

    assert adapter.posted_comments[0]["key"] == "WLTH-101"
    assert adapter.applied_labels[0]["label"] == "qe-gate-1-passed"
    # Transition ID resolved dynamically by name, never hardcoded.
    assert adapter.transitions_done[0]["transition_id"] == "11"
    assert by_type[PushType.TRANSITION].payload["resolved_transition_id"] == "11"


async def test_unavailable_transition_fails_cleanly(session, adapter):
    story = await _seed(session, adapter)
    await _accept_phase(session, story, Phase.REFINEMENT)
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    await workflow.signoff_gate(session, gate.id, "PO", "Product Owner", "ok")

    cfg = await settings_service.update_settings(
        session,
        {
            "gates": {
                "REFINEMENT": {
                    "auto_post_comment": False,
                    "apply_label": False,
                    "transition_name": "Nonexistent Status",
                }
            }
        },
        actor="test",
    )
    items = await push_service.handle_gate_signoff(
        session, adapter, story, gate, cfg, actor="PO"
    )
    assert len(items) == 1
    assert items[0].status == PushStatus.FAILED
    assert "not available" in items[0].last_error
    assert adapter.transitions_done == []


async def test_release_gate_attaches_audit_pack(session, adapter):
    story = await _seed(session, adapter)
    for phase in (Phase.REFINEMENT, Phase.DEVELOPMENT, Phase.TESTING, Phase.RELEASE):
        await _accept_phase(session, story, phase)
        gate = await workflow.gate_for_phase(session, story.id, phase)
        await workflow.signoff_gate(session, gate.id, "Approver", "QE Lead", "done")
    await session.commit()

    cfg = await settings_service.get_all(session)
    release_gate = await workflow.gate_for_phase(session, story.id, Phase.RELEASE)
    items = await push_service.handle_gate_signoff(
        session, adapter, story, release_gate, cfg, actor="Approver"
    )
    await session.commit()

    attachment = next(i for i in items if i.push_type == PushType.ATTACHMENT)
    assert attachment.status == PushStatus.SENT
    assert adapter.attachments[0]["filename"] == "WLTH-101-release-audit-pack.json"

    pack = json.loads(base64.b64decode(attachment.payload["content_b64"]))
    assert pack["story"]["jira_key"] == "WLTH-101"
    assert len(pack["gates"]) == 4
    assert all(g["status"] == "SIGNED_OFF" for g in pack["gates"])
    assert len(pack["agent_runs"]) == 26
    assert pack["audit_chain_verification"]["valid"] is True
