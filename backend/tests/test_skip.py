import pytest
from sqlalchemy import select

from app.models import GateStatus, Phase, RunStatus, Story
from app.services import settings_service, workflow
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))).scalar_one()


# ------------------------------------------------------------------ guardrail


async def test_cannot_disable_blocking_capable_agent(session):
    for key in ("financial_data_integrity", "test_execution_analyst"):
        with pytest.raises(ValueError):
            await settings_service.update_settings(
                session, {"agents": {"disabled": [key]}}, actor="test")


async def test_cannot_disable_unknown_agent(session):
    with pytest.raises(ValueError):
        await settings_service.update_settings(
            session, {"agents": {"disabled": ["not_a_real_agent"]}}, actor="test")


async def test_disable_advisory_agent_is_allowed(session):
    after = await settings_service.update_settings(
        session, {"agents": {"disabled": ["security_dast"]}}, actor="test")
    assert after["agents"]["disabled"] == ["security_dast"]
    assert await settings_service.disabled_agents(session) == {"security_dast"}


# ------------------------------------------------------------------ skip flow


async def test_disabled_agent_is_skipped_and_gate_still_ready(session, adapter):
    # Disable a mid-sequence advisory agent BEFORE the story is bootstrapped.
    await settings_service.update_settings(
        session, {"agents": {"disabled": ["three_amigos"]}}, actor="test")
    await session.commit()

    story = await _seed(session, adapter)

    ta = await workflow.latest_run(session, story.id, "three_amigos")
    assert ta.status == RunStatus.SKIPPED

    # The five active Refinement agents unlock in sequence, stepping over the
    # skipped Three Amigos (seq 5) so BDD (seq 6) unlocks after AC Advisor (seq 4).
    for key in ["story_quality", "fca_regulatory_impact", "consumer_duty_mapper",
                "compliance_ac_advisor", "bdd_generator"]:
        run = await workflow.latest_run(session, story.id, key)
        assert run.status == RunStatus.AWAITING_APPROVAL, f"{key} not unlocked"
        await workflow.approve_and_run(session, run.id, approver="PO")
        await workflow.accept_run(session, run.id, actor="PO")

    # Gate is ready even though Three Amigos never ran — SKIPPED counts as done.
    gate = await workflow.gate_for_phase(session, story.id, Phase.REFINEMENT)
    assert gate.status == GateStatus.READY_FOR_SIGNOFF
