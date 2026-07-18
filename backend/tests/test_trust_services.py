"""Operational Agent Health, Adversarial Challenger, and the eval harness."""

from sqlalchemy import select

from app.models import AgentRun, Phase, RunStatus, Story
from app.services import agent_health, challenger, evals, workflow
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


# ------------------------------------------------------- operational health


async def test_agent_health_aggregates_and_alerts(session, adapter):
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")

    # Three failed executions of one agent -> FAILURE_RATE alert.
    for i in range(3):
        session.add(AgentRun(
            story_id=story.id, agent_key="static_analysis",
            phase=Phase.DEVELOPMENT, sequence=3, attempt=i + 10,
            status=RunStatus.FAILED, prompt_version="v3",
        ))
    await session.flush()

    health = await agent_health.compute(session)
    by_key = {a["agent_key"]: a for a in health["agents"]}
    assert by_key["story_quality"]["executed"] == 1
    assert by_key["story_quality"]["failed"] == 0
    sa = by_key["static_analysis"]
    assert sa["failed"] == 3 and sa["failure_rate"] == 1.0
    assert any(a["kind"] == "FAILURE_RATE" and a["agent_key"] == "static_analysis"
               for a in health["alerts"])
    # Per-prompt-version reliability is tracked.
    assert sa["versions"][0]["version"] == "v3"
    assert health["summary"]["total_failed"] == 3


async def test_agent_health_flags_version_regression(session, adapter):
    story = await _seed(session, adapter)
    # v1: 3 clean executions; v2: 3 failures -> VERSION_REGRESSION alert.
    specs = [(RunStatus.COMPLETED, "v1")] * 3 + [(RunStatus.FAILED, "v2")] * 3
    for i, (status, ver) in enumerate(specs):
        session.add(AgentRun(
            story_id=story.id, agent_key="code_review",
            phase=Phase.DEVELOPMENT, sequence=4, attempt=i + 10,
            status=status, prompt_version=ver,
            output_json={"verdict": "PASS"} if status == RunStatus.COMPLETED else None,
        ))
    await session.flush()
    health = await agent_health.compute(session)
    assert any(a["kind"] == "VERSION_REGRESSION" and a["agent_key"] == "code_review"
               for a in health["alerts"])


# ------------------------------------------------------------- challenger


class _R:
    def __init__(self, phase, output):
        self.phase = phase
        self.output_json = {
            "verdict": "PASS", "release_blocking": False,
            "confidence": {"level": "HIGH", "caveats": []},
            "summary": "s", "findings": [], **output,
        }


def test_challenger_surfaces_the_case_against():
    latest = {
        "three_amigos": _R(Phase.REFINEMENT, {
            "confidence": {"level": "MEDIUM",
                           "caveats": ["No CI/CD artifacts were provided"]},
            "open_questions": [
                {"question": "What reconciliation tolerance?", "blocking": True},
            ],
        }),
        "bdd_generator": _R(Phase.REFINEMENT, {
            "verdict": "WARN",
            "findings": [{"title": "1 uncovered card", "detail": "d",
                          "severity": "HIGH"}],
            "coverage": {"uncovered_examples": ["EX-2.2"]},
        }),
    }
    out = challenger.deterministic_challenges(latest, Phase.REFINEMENT)
    kinds = [c["kind"] for c in out]
    assert "BLOCKING_QUESTION" in kinds
    assert "SEVERE_FINDING" in kinds        # WARN verdict atop a HIGH finding
    assert "UNCOVERED_EVIDENCE" in kinds
    assert "SELF_REPORTED_CAVEAT" in kinds
    # Strongest-first ordering: contradictions/blockers before caveats.
    assert kinds.index("BLOCKING_QUESTION") < kinds.index("SELF_REPORTED_CAVEAT")


def test_challenger_includes_cross_agent_contradictions():
    latest = {
        "financial_data_integrity": _R(Phase.TESTING, {
            "verdict": "FAIL", "release_blocking": True,
        }),
        "deployment_risk": _R(Phase.RELEASE, {"recommendation": "GO"}),
    }
    # Challenging the TESTING gate must surface the financial-vs-GO clash.
    out = challenger.deterministic_challenges(latest, Phase.TESTING)
    assert any(c["kind"] == "CONTRADICTION" for c in out)


async def test_challenges_endpoint_shape(session, adapter):
    story = await _seed(session, adapter)
    result = await challenger.challenges_for_gate(session, story.id, Phase.REFINEMENT)
    assert result["phase"] == "REFINEMENT"
    assert result["generated_by"] == "deterministic"
    assert isinstance(result["challenges"], list)


# ------------------------------------------------------------ eval harness


def test_financial_golden_cases_all_pass():
    card = evals.run_agent_evals("financial_data_integrity")
    assert card["cases"] == 4
    assert card["failed"] == 0, [
        r for r in card["results"] if not r["passed"]
    ]


def test_eval_grading_operators():
    out = {"verdict": "FAIL", "checks": [{"variance": "1.63"}],
           "summary": "release-blocking, no override", "items": [1, 2]}
    results = evals.grade(out, [
        {"path": "verdict", "equals": "FAIL"},
        {"path": "checks.0.variance", "approx": 1.63, "tol": 0.001},
        {"path": "summary", "contains": "no override"},
        {"path": "items", "min_len": 2},
        {"path": "verdict", "equals": "PASS"},  # deliberate miss
    ])
    assert [r["passed"] for r in results] == [True, True, True, True, False]


def test_golden_registry_lists_agents():
    assert "financial_data_integrity" in evals.available_agents()
