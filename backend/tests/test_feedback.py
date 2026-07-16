from app.models import AgentRun, Phase, RunStatus, Story
from app.services import feedback


async def _bare_story(session) -> Story:
    """A story with no bootstrapped runs, so the test controls the run rows."""
    story = Story(jira_key="FB-1", summary="feedback fixture")
    session.add(story)
    await session.flush()
    return story


async def test_agent_performance_aggregates_human_decisions(session, adapter):
    story = await _bare_story(session)

    # story_quality: accepted once.
    session.add(AgentRun(
        story_id=story.id, agent_key="story_quality", phase=Phase.REFINEMENT,
        sequence=1, attempt=1, status=RunStatus.ACCEPTED, output_json={"verdict": "WARN"}))
    # apex_coverage: rejected (attempt 1) then re-run-with-guidance accepted (attempt 2).
    r2 = AgentRun(
        story_id=story.id, agent_key="apex_coverage", phase=Phase.DEVELOPMENT,
        sequence=2, attempt=1, status=RunStatus.REJECTED,
        decision_reason="coverage numbers wrong", output_json={"verdict": "FAIL"})
    session.add(r2)
    await session.flush()
    session.add(AgentRun(
        story_id=story.id, agent_key="apex_coverage", phase=Phase.DEVELOPMENT,
        sequence=2, attempt=2, parent_run_id=r2.id, guidance="add a 200-record bulk test",
        status=RunStatus.ACCEPTED, output_json={"verdict": "PASS"}))
    await session.flush()

    perf = await feedback.agent_performance(session)
    by_key = {a["agent_key"]: a for a in perf["agents"]}

    sq = by_key["story_quality"]
    assert sq["accepted"] == 1 and sq["trust_score"] == 100
    assert sq["verdicts"]["WARN"] == 1

    ac = by_key["apex_coverage"]
    assert (ac["accepted"], ac["rejected"], ac["reruns"]) == (1, 1, 1)
    assert ac["reject_reasons"] == ["coverage numbers wrong"]
    assert ac["guidance_samples"] == ["add a 200-record bulk test"]
    assert ac["verdicts"] == {"PASS": 1, "WARN": 0, "FAIL": 1}
    # denom = accepted(1) + rejected(1) + reruns(1) = 3 -> trust 33.
    assert ac["trust_score"] == 33
    assert ac["avg_attempts"] == 2.0

    assert perf["summary"]["total_accepted"] == 2
    assert perf["summary"]["total_rejected"] == 1
    assert perf["summary"]["total_reruns"] == 1
    # Lowest trust first -> apex_coverage tops "needs attention".
    assert perf["needs_attention"][0]["agent_key"] == "apex_coverage"


async def test_no_decisions_is_empty(session, adapter):
    await _bare_story(session)
    perf = await feedback.agent_performance(session)
    assert perf["summary"]["total_accepted"] == 0
    assert perf["summary"]["overall_acceptance_rate"] is None
    assert perf["needs_attention"] == []
