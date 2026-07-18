"""The gate-rejection recovery loop: reject → re-run an ACCEPTED agent with
guidance → re-accept → the gate returns to READY_FOR_SIGNOFF. Previously a
dead-end: at gate-ready time every run is ACCEPTED, and ACCEPTED runs could
not be re-run — a rejected gate left the story stuck."""

from sqlalchemy import select

from app.models import GateStatus, Phase, RunStatus, Story
from app.services import workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import sync_service


async def _ready_gate(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()
    for agent in agents_for_phase(Phase.REFINEMENT):
        run = await workflow.latest_run(session, story.id, agent.key)
        await workflow.approve_and_run(session, run.id, approver="Test Lead")
        await workflow.accept_run(session, run.id, actor="Test Lead")
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    assert gate.status == GateStatus.READY_FOR_SIGNOFF
    return story, gate


async def test_reject_then_rerun_then_gate_ready_again(session, adapter):
    story, gate = await _ready_gate(session, adapter)

    # 1. The PO rejects the gate with a rationale.
    await workflow.reject_gate(
        session, gate.id, "Pat", "Product Owner",
        "BDD scenarios miss the pending-account display behaviour",
    )
    assert gate.status == GateStatus.REJECTED

    # 2. Recovery: re-run the offending agent even though it is ACCEPTED.
    accepted = await workflow.latest_run(session, story.id, "bdd_generator")
    assert accepted.status == RunStatus.ACCEPTED
    child = await workflow.request_rerun(
        session, accepted.id, "Pat",
        "Address the gate rejection: cover pending-account display behaviour",
    )
    # The acceptance is immutable history; the child supersedes it as latest.
    assert accepted.status == RunStatus.ACCEPTED
    assert child.attempt == accepted.attempt + 1
    assert child.status == RunStatus.AWAITING_APPROVAL
    assert child.parent_run_id == accepted.id

    # 3. While the new attempt is undecided the gate must NOT be signable.
    latest = await workflow.latest_run(session, story.id, "bdd_generator")
    assert latest.id == child.id

    # 4. Approve, run and accept the new attempt → gate re-readies.
    await workflow.approve_and_run(session, child.id, approver="Test Lead")
    await workflow.accept_run(session, child.id, actor="Test Lead")
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    assert gate.status == GateStatus.READY_FOR_SIGNOFF  # recovered

    # 5. And the sign-off now proceeds on the new evidence.
    signed = await workflow.signoff_gate(
        session, gate.id, "Pat", "Product Owner", "Re-reviewed — scenarios now cover it"
    )
    assert signed.status == GateStatus.SIGNED_OFF
