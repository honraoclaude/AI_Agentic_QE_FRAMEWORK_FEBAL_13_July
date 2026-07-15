from sqlalchemy import select

from app.models import Phase, Story
from app.services import work_service, workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import sync_service


async def _seed(session, adapter) -> None:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()


async def _story(session, key) -> Story:
    return (
        await session.execute(select(Story).where(Story.jira_key == key))
    ).scalar_one()


async def _advance_to_gate_ready(session, story, phase):
    for agent in agents_for_phase(phase):
        run = await workflow.latest_run(session, story.id, agent.key)
        await workflow.approve_and_run(session, run.id, approver="QE Lead")
        await workflow.accept_run(session, run.id, actor="QE Lead")


async def test_operator_sees_run_approvals(session, adapter):
    await _seed(session, adapter)
    work = await work_service.get_work(session, "QE Lead")
    # Each of the 8 stories has a first Refinement agent awaiting approval.
    approvals = [i for i in work["items"] if i["kind"] == "RUN_APPROVAL"]
    assert len(approvals) == 8
    assert all(i["action"] == "APPROVE_RUN" for i in approvals)
    assert work["counts"]["RUN_APPROVAL"] == 8


async def test_non_operator_sees_no_run_actions(session, adapter):
    await _seed(session, adapter)
    for role in ("Product Owner", "Tech Lead", "Business Stakeholder", "Compliance Officer"):
        work = await work_service.get_work(session, role)
        assert all(
            i["kind"] not in ("RUN_APPROVAL", "RUN_DECISION", "PUSH_APPROVAL", "PUSH_RETRY")
            for i in work["items"]
        )


async def test_completed_run_appears_as_decision(session, adapter):
    await _seed(session, adapter)
    story = await _story(session, "WLTH-101")
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="QE Lead")

    work = await work_service.get_work(session, "QE Lead")
    decisions = [i for i in work["items"] if i["kind"] == "RUN_DECISION"]
    assert any(i["entity_id"] == run.id for i in decisions)


async def test_gate1_visible_to_po_and_qe_only(session, adapter):
    await _seed(session, adapter)
    story = await _story(session, "WLTH-101")
    await _advance_to_gate_ready(session, story, Phase.REFINEMENT)
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)

    po = await work_service.get_work(session, "Product Owner")
    qe = await work_service.get_work(session, "QE Lead")
    tech = await work_service.get_work(session, "Tech Lead")

    assert any(i["entity_id"] == gate.id for i in po["items"])
    assert any(i["entity_id"] == gate.id for i in qe["items"])
    assert all(i["entity_id"] != gate.id for i in tech["items"])


async def test_gate4_compliance_only_when_fca_high(session, adapter):
    await _seed(session, adapter)

    # WLTH-101 is FCA HIGH; WLTH-106 is FCA LOW. Drive both to the Release gate.
    for key in ("WLTH-101", "WLTH-106"):
        story = await _story(session, key)
        for phase in (Phase.REFINEMENT, Phase.DEVELOPMENT, Phase.TESTING):
            await _advance_to_gate_ready(session, story, phase)
            gate = await workflow.gate_for_phase(session, story.id, phase)
            await workflow.signoff_gate(session, gate.id, "Approver", "QE Lead", "ok")
        await _advance_to_gate_ready(session, story, Phase.RELEASE)

    high = await _story(session, "WLTH-101")
    low = await _story(session, "WLTH-106")
    high_gate = await workflow.gate_for_phase(session, high.id, Phase.RELEASE)
    low_gate = await workflow.gate_for_phase(session, low.id, Phase.RELEASE)

    compliance = await work_service.get_work(session, "Compliance Officer")
    ids = {i["entity_id"] for i in compliance["items"]}
    assert high_gate.id in ids       # HIGH -> Compliance required
    assert low_gate.id not in ids    # LOW  -> Compliance not required


async def test_invalid_role_rejected():
    assert work_service.is_valid_role("QE Lead") is True
    assert work_service.is_valid_role("Intern") is False
