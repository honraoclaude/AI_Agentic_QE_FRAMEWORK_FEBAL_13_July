"""Cross-Agent Referee + Release Health Index.

A cross-cutting synthesis layer over ALL of a story's agent runs. It does two
things the individual agents cannot, because they only see their own slice:

1. Release Health Index — one confidence-weighted score (0-100) + band, with a
   per-phase breakdown, the active blockers and the least-confident calls.
2. Cross-Agent Referee — deterministic checks that flag *contradictions between
   agents* (e.g. "deployable" vs coverage below floor; a GO recommendation while
   Financial Integrity failed).

Pure reads of the persisted output_json — no model calls — so it is deterministic
and cheap, and it activates the per-agent `confidence` field.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, RunStatus
from ..models.enums import PHASE_ORDER
from .agents.output_schemas import severity_rank
from .agents.registry import get_agent

VERDICT_SCORE = {"PASS": 100, "WARN": 65, "FAIL": 25}
CONF_WEIGHT = {"HIGH": 1.0, "MEDIUM": 0.8, "LOW": 0.6}


async def _latest_runs(session: AsyncSession, story_id: str) -> dict[str, AgentRun]:
    """The latest run per agent that has produced output (COMPLETED or ACCEPTED)."""
    rows = (
        (
            await session.execute(
                select(AgentRun)
                .where(
                    AgentRun.story_id == story_id,
                    AgentRun.status.in_([RunStatus.COMPLETED, RunStatus.ACCEPTED]),
                )
                .order_by(AgentRun.attempt.asc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, AgentRun] = {}
    for r in rows:
        if r.output_json:
            latest[r.agent_key] = r  # later attempt overwrites earlier
    return latest


def _out(run: AgentRun) -> dict:
    return run.output_json or {}


def _verdict(o: dict) -> str:
    return o.get("verdict") or "WARN"


def _conf(o: dict) -> str:
    c = o.get("confidence") or {}
    return c.get("level") or "MEDIUM"


def _agent_name(key: str) -> str:
    try:
        return get_agent(key).name
    except KeyError:
        return key


# ---------------------------------------------------------------- health index


def compute_health(latest: dict[str, AgentRun]) -> dict:
    runs = list(latest.values())
    if not runs:
        return {
            "score": None, "band": "NO_DATA", "assurance": None,
            "counts": {"pass": 0, "warn": 0, "fail": 0},
            "phase_breakdown": [], "blockers": [], "least_confident": [],
            "agents_evaluated": 0,
        }

    num = den = 0.0
    counts = {"pass": 0, "warn": 0, "fail": 0}
    blockers, least_confident = [], []
    by_phase: dict[str, list[float]] = {}
    conf_w_sum = 0.0

    for key, r in latest.items():
        o = _out(r)
        verdict = _verdict(o)
        conf = _conf(o)
        blocking = bool(o.get("release_blocking"))
        vs = 0 if blocking else VERDICT_SCORE.get(verdict, 65)
        w = CONF_WEIGHT.get(conf, 0.8)
        num += vs * w
        den += w
        conf_w_sum += w
        counts[verdict.lower()] = counts.get(verdict.lower(), 0) + 1
        by_phase.setdefault(r.phase.value, []).append(vs)
        if blocking:
            blockers.append({"agent": _agent_name(key), "phase": r.phase.value,
                             "summary": o.get("summary", "")[:160]})
        if conf == "LOW":
            least_confident.append({"agent": _agent_name(key), "verdict": verdict,
                                    "phase": r.phase.value})

    score = round(num / den) if den else 0
    if blockers:
        band = "BLOCKED"
        score = min(score, 30)
    elif score >= 80:
        band = "HEALTHY"
    elif score >= 55:
        band = "AT_RISK"
    else:
        band = "CRITICAL"

    assurance_w = conf_w_sum / len(runs)
    assurance = "HIGH" if assurance_w >= 0.95 else "MEDIUM" if assurance_w >= 0.75 else "LOW"

    # The single worst finding across all agents — enabled by the one calibrated
    # severity scale (severity_rank compares across every agent's vocabulary).
    worst_sev, worst_rank = None, 0
    for r in runs:
        for f in _out(r).get("findings") or []:
            rk = severity_rank(f.get("severity"))
            if rk > worst_rank:
                worst_rank, worst_sev = rk, f.get("severity")

    phase_breakdown = [
        {"phase": p, "score": round(sum(by_phase[p]) / len(by_phase[p]))}
        for p in sorted(by_phase, key=lambda x: PHASE_ORDER.index(_phase_enum(x)))
    ]
    return {
        "score": score, "band": band, "assurance": assurance,
        "counts": counts, "phase_breakdown": phase_breakdown,
        "blockers": blockers, "least_confident": least_confident,
        "worst_finding_severity": worst_sev,
        "agents_evaluated": len(runs),
    }


def _phase_enum(value: str):
    from ..models.enums import Phase
    return Phase(value)


# ---------------------------------------------------------------- referee


def _inconsistency(rule, severity, agents, detail, recommendation):
    return {"rule": rule, "severity": severity, "agents": agents,
            "detail": detail, "recommendation": recommendation}


def find_inconsistencies(latest: dict[str, AgentRun]) -> list[dict]:
    """Deterministic cross-agent contradiction checks. Each reads fields we know
    the agents emit; a rule is skipped if its agents haven't run."""
    o = {k: _out(r) for k, r in latest.items()}
    issues: list[dict] = []

    # 1. Deployable vs coverage below floor.
    if "apex_coverage" in o and "deployability_validation" in o:
        cov_ok = o["apex_coverage"].get("deployable") and o["apex_coverage"].get("gate_passed", True)
        dep_ok = o["deployability_validation"].get("deployable")
        if dep_ok and cov_ok is False:
            issues.append(_inconsistency(
                "deployable_vs_coverage", "HIGH",
                ["Apex Test Coverage", "Deployability Validation"],
                "Deployability reports the package deploys, but Apex Coverage fails its gate (below floor / new-code target).",
                "Reconcile: a deploy that passes validation can still ship undertested code — hold on coverage."))

    # 2. Financial failure vs GO recommendation.
    if "financial_data_integrity" in o and "deployment_risk" in o:
        fin_bad = o["financial_data_integrity"].get("release_blocking") or _verdict(o["financial_data_integrity"]) == "FAIL"
        if fin_bad and o["deployment_risk"].get("recommendation") == "GO":
            issues.append(_inconsistency(
                "financial_vs_go", "HIGH",
                ["Financial Data Integrity", "Deployment Risk & Go/No-Go"],
                "Financial Data Integrity failed (release-blocking) yet the Go/No-Go recommends GO.",
                "A financial-integrity failure cannot be a GO — escalate the risk assessment."))

    # 3. E2E journey failed but no defect raised.
    if "integration_e2e_journey" in o and "defect_triage" in o:
        e2e_fail = any(j.get("status") == "FAIL" for j in o["integration_e2e_journey"].get("journeys", []))
        no_defect = not o["defect_triage"].get("suggested_defects")
        if e2e_fail and no_defect:
            issues.append(_inconsistency(
                "e2e_fail_no_defect", "MEDIUM",
                ["Integration & E2E Journey", "Defect Triage & Root-Cause"],
                "An end-to-end journey failed but Defect Triage raised no defect for it.",
                "Confirm the E2E failure is triaged — a real cross-cloud defect may be unlogged."))

    # 4. Security HIGH while regression narrowed.
    if "security_dast" in o and "regression_scope" in o:
        risky = o["security_dast"].get("risk_rating") in ("HIGH", "CRITICAL")
        narrowed = bool(o["regression_scope"].get("excluded"))
        if risky and narrowed:
            issues.append(_inconsistency(
                "security_vs_regression", "MEDIUM",
                ["Security Testing (DAST)", "Regression Scope"],
                "Security risk is HIGH/CRITICAL while Regression Scope excludes areas from testing.",
                "Re-check the excluded areas are not reachable from the security finding."))

    # 5. AC covered but no test scenario.
    if "ac_compliance" in o:
        untested = [m for m in o["ac_compliance"].get("ac_mapping", [])
                    if m.get("status") == "COVERED" and not (m.get("test_coverage") or {}).get("has_scenario")]
        if untested:
            issues.append(_inconsistency(
                "covered_untested", "MEDIUM",
                ["AC Compliance Checker", "BDD Scenario Generator"],
                f"{len(untested)} acceptance criterion/criteria are implemented (COVERED) but have no BDD scenario.",
                "Add scenarios — implemented-but-untested is a silent coverage gap."))

    # 6. Test run failed but regression scope reported green.
    if "test_execution_analyst" in o and "regression_scope" in o:
        if _verdict(o["test_execution_analyst"]) == "FAIL" and _verdict(o["regression_scope"]) == "PASS":
            issues.append(_inconsistency(
                "tests_vs_regression", "LOW",
                ["Test Execution Analyst", "Regression Scope"],
                "Test execution has failures while Regression Scope reads green.",
                "Informational — ensure the regression suite covers the failing area."))

    # 7. Release-blocking call made with LOW confidence.
    for key, out in o.items():
        if out.get("release_blocking") and _conf(out) == "LOW":
            issues.append(_inconsistency(
                "low_confidence_blocker", "HIGH", [_agent_name(key)],
                f"{_agent_name(key)} raised a release-blocking result with LOW confidence.",
                "Verify the evidence before treating this as a hard block."))

    sev_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    issues.sort(key=lambda i: sev_rank.get(i["severity"], 3))
    return issues


async def assess(session: AsyncSession, story_id: str) -> dict:
    latest = await _latest_runs(session, story_id)
    health = compute_health(latest)
    inconsistencies = find_inconsistencies(latest)
    health["inconsistencies"] = inconsistencies
    health["inconsistency_count"] = len(inconsistencies)
    return health
