import pytest
from sqlalchemy import select

from app.models import (
    AgentRun,
    Gate,
    GateStatus,
    Phase,
    RunStatus,
    Story,
)
from app.services import workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import sync_service


async def _seed_one_story(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()
    return story


async def _runs_for(session, story_id, phase=None) -> list[AgentRun]:
    stmt = select(AgentRun).where(AgentRun.story_id == story_id)
    if phase:
        stmt = stmt.where(AgentRun.phase == phase)
    return list((await session.execute(stmt)).scalars())


async def _accept_all_phase_agents(session, story, phase) -> None:
    """Approve+run then accept each agent in sequence for a phase."""
    for agent in agents_for_phase(phase):
        run = await workflow.latest_run(session, story.id, agent.key)
        assert run.status == RunStatus.AWAITING_APPROVAL, (
            f"{agent.key} expected AWAITING_APPROVAL, got {run.status}"
        )
        await workflow.approve_and_run(session, run.id, approver="Test Lead")
        assert run.status == RunStatus.COMPLETED
        await workflow.accept_run(session, run.id, actor="Test Lead")
        assert run.status == RunStatus.ACCEPTED
    await session.commit()


async def test_story_bootstrap_proposes_agents_and_gates(session, adapter):
    story = await _seed_one_story(session, adapter)

    gates = list(
        (await session.execute(select(Gate).where(Gate.story_id == story.id))).scalars()
    )
    assert len(gates) == 4
    assert all(g.status == GateStatus.LOCKED for g in gates)

    runs = await _runs_for(session, story.id, Phase.REFINEMENT)
    assert len(runs) == 6
    by_seq = {r.sequence: r for r in runs}
    # Nothing runs automatically: first agent merely awaits human approval,
    # every later agent stays locked until its predecessor is accepted.
    assert by_seq[1].status == RunStatus.AWAITING_APPROVAL
    assert all(by_seq[s].status == RunStatus.PROPOSED for s in range(2, 7))


async def test_agent_cannot_run_without_approval_state(session, adapter):
    story = await _seed_one_story(session, adapter)
    runs = await _runs_for(session, story.id, Phase.REFINEMENT)
    locked = next(r for r in runs if r.status == RunStatus.PROPOSED)

    with pytest.raises(workflow.WorkflowError):
        await workflow.approve_and_run(session, locked.id, approver="Test Lead")


async def test_approval_requires_named_approver(session, adapter):
    story = await _seed_one_story(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    with pytest.raises(workflow.WorkflowError):
        await workflow.approve_and_run(session, run.id, approver="   ")


async def test_accept_unlocks_next_agent(session, adapter):
    story = await _seed_one_story(session, adapter)
    first = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, first.id, approver="Test Lead")
    await workflow.accept_run(session, first.id, actor="Test Lead")

    second = await workflow.latest_run(session, story.id, "fca_regulatory_impact")
    assert second.status == RunStatus.AWAITING_APPROVAL
    later = await workflow.latest_run(session, story.id, "bdd_generator")
    assert later.status == RunStatus.PROPOSED


async def test_reject_requires_reason(session, adapter):
    story = await _seed_one_story(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    with pytest.raises(workflow.WorkflowError):
        await workflow.reject_run(session, run.id, actor="Test Lead", reason="")


async def test_rerun_with_guidance_creates_child_awaiting_approval(session, adapter):
    story = await _seed_one_story(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")

    child = await workflow.request_rerun(
        session, run.id, actor="Test Lead", guidance="Focus on Consumer Duty angles"
    )
    assert run.status == RunStatus.RERUN_REQUESTED
    assert child.status == RunStatus.AWAITING_APPROVAL
    assert child.attempt == 2
    assert child.parent_run_id == run.id
    assert child.guidance == "Focus on Consumer Duty angles"

    # Guidance is injected into the next execution.
    await workflow.approve_and_run(session, child.id, approver="Test Lead")
    assert child.output_json["guidance_applied"] == "Focus on Consumer Duty angles"


async def test_gate_ready_only_after_all_accepted_then_signoff_advances_phase(
    session, adapter
):
    story = await _seed_one_story(session, adapter)
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)

    # Sign-off before ready is illegal.
    with pytest.raises(workflow.WorkflowError):
        await workflow.signoff_gate(session, gate.id, "PO", "Product Owner", "lgtm")

    await _accept_all_phase_agents(session, story, Phase.REFINEMENT)
    assert gate.status == GateStatus.READY_FOR_SIGNOFF

    # Rationale is mandatory.
    with pytest.raises(workflow.WorkflowError):
        await workflow.signoff_gate(session, gate.id, "PO", "Product Owner", "  ")

    await workflow.signoff_gate(
        session,
        gate.id,
        approver_name="Priya Sharma",
        approver_role="Product Owner",
        rationale="INVEST compliant, FCA impact classified HIGH, scenarios approved.",
    )
    assert gate.status == GateStatus.SIGNED_OFF
    assert gate.evidence and len(gate.evidence["accepted_runs"]) == 6

    # Story advanced exactly one phase; development agents proposed.
    assert story.current_phase == Phase.DEVELOPMENT
    dev_runs = await _runs_for(session, story.id, Phase.DEVELOPMENT)
    assert len(dev_runs) == 5
    assert (
        await workflow.latest_run(session, story.id, "ac_compliance")
    ).status == RunStatus.AWAITING_APPROVAL

    # Double sign-off is illegal.
    with pytest.raises(workflow.WorkflowError):
        await workflow.signoff_gate(session, gate.id, "PO", "Product Owner", "again")


async def test_release_blocking_finding_blocks_gate_with_no_override(
    session, adapter, monkeypatch
):
    """FCA-scenario / financial-data-integrity failures: gate never becomes
    ready, and there is no API surface to force it."""
    story = await _seed_one_story(session, adapter)

    # Walk to TESTING phase.
    for phase in (Phase.REFINEMENT, Phase.DEVELOPMENT):
        await _accept_all_phase_agents(session, story, phase)
        gate = await workflow.gate_for_phase(session, story.id, phase)
        await workflow.signoff_gate(session, gate.id, "QE Lead", "QE Lead", "ok")
    assert story.current_phase == Phase.TESTING

    # Make the Financial Data Integrity agent emit a blocking failure.
    from app.services.agents import engine as engine_mod

    real_execute = engine_mod.execute

    async def blocking_execute(
        run, story_, agent, guidance=None, artifacts=None, upstream=None
    ):
        result = await real_execute(run, story_, agent, guidance, artifacts, upstream)
        if agent.key == "financial_data_integrity":
            result["output"]["verdict"] = "FAIL"
            result["output"]["release_blocking"] = True
            result["output"]["findings"] = [
                "Household rollup mismatch: expected 1,250,000.00 got 1,249,998.37"
            ]
        return result

    monkeypatch.setattr("app.services.workflow.engine.execute", blocking_execute)

    await _accept_all_phase_agents(session, story, Phase.TESTING)
    gate = await workflow.gate_for_phase(session, story.id, Phase.TESTING)
    assert gate.status == GateStatus.LOCKED  # blocked, not ready

    with pytest.raises(workflow.WorkflowError):
        await workflow.signoff_gate(session, gate.id, "QE Lead", "QE Lead", "force it")


async def test_full_lifecycle_to_release(session, adapter):
    story = await _seed_one_story(session, adapter)
    roles = {
        Phase.REFINEMENT: ("Priya Sharma", "Product Owner"),
        Phase.DEVELOPMENT: ("Marcus Chen", "Tech Lead"),
        Phase.TESTING: ("Honra O", "QE Lead"),
        Phase.RELEASE: ("Amelia Grant", "Compliance Officer"),
    }
    for phase in (Phase.REFINEMENT, Phase.DEVELOPMENT, Phase.TESTING, Phase.RELEASE):
        assert story.current_phase == phase
        await _accept_all_phase_agents(session, story, phase)
        gate = await workflow.gate_for_phase(session, story.id, phase)
        name, role = roles[phase]
        await workflow.signoff_gate(session, gate.id, name, role, f"{phase.value} done")

    assert story.released is True
    assert story.current_phase == Phase.RELEASE

    # 26 accepted runs (6 Refinement + 5 Development + 7 Testing + 8 Release).
    runs = await _runs_for(session, story.id)
    assert len(runs) == 26
    assert all(r.status == RunStatus.ACCEPTED for r in runs)
