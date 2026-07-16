from sqlalchemy import select

from app.models import Phase, Story
from app.services import referee, workflow
from app.services.agents.registry import agents_for_phase
from app.services.jira import sync_service


class _R:
    """Lightweight stand-in for AgentRun (referee reads output_json / phase / key)."""

    def __init__(self, phase, output):
        self.phase = phase
        self.output_json = output


def _run(verdict="PASS", conf="HIGH", blocking=False, phase=Phase.TESTING, **extra):
    out = {"verdict": verdict, "confidence": {"level": conf, "rationale": "x", "caveats": []},
           "release_blocking": blocking, "summary": "s", **extra}
    return _R(phase, out)


# ------------------------------------------------------------------ health index


def test_health_healthy_when_all_pass():
    latest = {"a": _run("PASS"), "b": _run("PASS"), "c": _run("PASS")}
    h = referee.compute_health(latest)
    assert h["score"] == 100 and h["band"] == "HEALTHY"
    assert h["counts"]["pass"] == 3


def test_health_at_risk_on_warns():
    latest = {"a": _run("WARN"), "b": _run("WARN"), "c": _run("PASS")}
    h = referee.compute_health(latest)
    assert h["band"] in ("AT_RISK", "HEALTHY")
    assert 55 <= h["score"] < 100


def test_blocker_forces_blocked_band():
    latest = {"a": _run("PASS"), "fin": _run("FAIL", blocking=True)}
    h = referee.compute_health(latest)
    assert h["band"] == "BLOCKED" and h["score"] <= 30
    assert h["blockers"] and h["blockers"][0]["summary"] is not None


def test_low_confidence_lowers_assurance():
    latest = {"a": _run("PASS", conf="LOW"), "b": _run("PASS", conf="LOW")}
    h = referee.compute_health(latest)
    assert h["assurance"] == "LOW"
    assert h["least_confident"] and len(h["least_confident"]) == 2


# ------------------------------------------------------------------ referee


def test_inconsistency_financial_vs_go():
    latest = {
        "financial_data_integrity": _run("FAIL", blocking=True),
        "deployment_risk": _run("PASS", recommendation="GO"),
    }
    issues = referee.find_inconsistencies(latest)
    assert any(i["rule"] == "financial_vs_go" and i["severity"] == "HIGH" for i in issues)


def test_inconsistency_deployable_vs_coverage():
    latest = {
        "apex_coverage": _run("FAIL", deployable=False, gate_passed=False),
        "deployability_validation": _run("PASS", deployable=True),
    }
    issues = referee.find_inconsistencies(latest)
    assert any(i["rule"] == "deployable_vs_coverage" for i in issues)


def test_inconsistency_low_confidence_blocker():
    latest = {"test_execution_analyst": _run("FAIL", conf="LOW", blocking=True)}
    issues = referee.find_inconsistencies(latest)
    assert any(i["rule"] == "low_confidence_blocker" for i in issues)


def test_no_inconsistencies_when_consistent():
    latest = {"a": _run("PASS"), "b": _run("PASS")}
    assert referee.find_inconsistencies(latest) == []


# ------------------------------------------------------------------ integration


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))).scalar_one()


async def test_assess_over_real_runs(session, adapter):
    story = await _seed(session, adapter)
    # Run + accept the whole Refinement phase to create real output_json rows.
    for agent in agents_for_phase(Phase.REFINEMENT):
        run = await workflow.latest_run(session, story.id, agent.key)
        await workflow.approve_and_run(session, run.id, approver="PO")
        await workflow.accept_run(session, run.id, actor="PO")
    await session.commit()

    h = await referee.assess(session, story.id)
    assert h["agents_evaluated"] == 6
    assert h["score"] is not None and h["band"] in ("HEALTHY", "AT_RISK", "CRITICAL", "BLOCKED")
    assert "inconsistencies" in h and isinstance(h["inconsistency_count"], int)
    assert any(p["phase"] == "REFINEMENT" for p in h["phase_breakdown"])
