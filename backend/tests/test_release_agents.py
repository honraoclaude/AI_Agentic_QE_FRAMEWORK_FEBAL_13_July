"""Five industry-standard Release-phase agents: Deployment Risk & Go/No-Go,
Change Management/CAB, Post-Deployment Verification, Release Notes, and
Post-Release Monitoring & Hypercare. Advisory, non-blocking, seq 4-8.
"""

from app.models import Phase
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    OUTPUT_SCHEMAS,
    ChangeManagementOutput,
    DeploymentRiskOutput,
    MonitoringHypercareOutput,
    PostDeployVerificationOutput,
    ReleaseNotesOutput,
    ReleaseReadinessOutput,
)
from app.services.agents.registry import agents_for_phase


def _story(fca="HIGH"):
    class _FI:
        value = fca

    class _S:
        jira_key = "WLTH-101"
        summary = "Household rollup recalculates client-facing balance"
        acceptance_criteria = ["Rollup sums active accounts", "Closed accounts excluded"]
        fca_impact = _FI()
        cloud = None

    return _S()


META = {"kind": "METADATA", "filename": "p.json", "summary": "",
        "parsed": {"components": ["ApexClass: HouseholdRollupService", "Flow: HouseholdReassignment", "ApexTrigger: FinancialAccountTrigger"]}}


def test_release_phase_has_eight_agents_in_order():
    seq = [a.key for a in agents_for_phase(Phase.RELEASE)]
    assert seq == [
        "release_readiness", "uat_signoff_coordinator", "regulatory_audit_trail",
        "deployment_risk", "change_management", "post_deploy_verification",
        "release_notes", "monitoring_hypercare",
    ]


def test_all_five_registered():
    for key in ("deployment_risk", "change_management", "post_deploy_verification",
                "release_notes", "monitoring_hypercare"):
        assert key in OUTPUT_SCHEMAS and key in GENERATORS


def test_deployment_risk_conditional_go_on_concerns():
    body = build("deployment_risk", _story("HIGH"), None, artifacts=[META])
    parsed = DeploymentRiskOutput.model_validate(body)
    assert parsed.recommendation in ("GO", "CONDITIONAL_GO", "NO_GO")
    assert 0 <= parsed.risk_score <= 100
    assert parsed.factors and parsed.blast_radius
    # HIGH FCA impact -> at least a CONCERN -> conditional go with conditions.
    assert parsed.recommendation == "CONDITIONAL_GO" and parsed.conditions
    assert parsed.release_blocking is False


def test_change_management_normal_change_for_high_fca():
    body = build("change_management", _story("HIGH"), None, artifacts=[META])
    parsed = ChangeManagementOutput.model_validate(body)
    assert parsed.change_type == "NORMAL"
    assert any(a.role == "Compliance Officer" for a in parsed.approvers)
    assert parsed.affected_services
    assert parsed.release_blocking is False


def test_post_deploy_verification_defines_checks_and_criteria():
    bdd = build("bdd_generator", _story(), None, artifacts=[], upstream=[])
    up = [{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd}]
    body = build("post_deploy_verification", _story(), None, artifacts=[META], upstream=up)
    parsed = PostDeployVerificationOutput.model_validate(body)
    assert parsed.checks and any(c.priority == "P1" for c in parsed.checks)
    assert parsed.go_live_criteria and parsed.abort_criteria
    assert parsed.release_blocking is False


def test_release_notes_from_metadata_and_acs():
    body = build("release_notes", _story(), None, artifacts=[META], upstream=[])
    parsed = ReleaseNotesOutput.model_validate(body)
    assert parsed.changes and parsed.acceptance_criteria_delivered
    assert parsed.version.startswith("WLTH-101")
    assert parsed.release_blocking is False


def _up(agent_key, verdict, blocking=False, **extra):
    out = {"verdict": verdict, "release_blocking": blocking,
           "confidence": {"level": "HIGH", "rationale": "x", "caveats": []},
           "summary": f"{agent_key} says {verdict}", **extra}
    return {"agent_key": agent_key, "agent_name": agent_key, "output": out}


def test_release_readiness_grounded_in_upstream():
    # A failing (blocking) financial result + a warning coverage result.
    upstream = [
        _up("ac_compliance", "PASS"),
        _up("apex_coverage", "WARN", deployable=True, gate_passed=False),
        _up("financial_data_integrity", "FAIL", blocking=True),
        _up("test_execution_analyst", "PASS"),
    ]
    body = build("release_readiness", _story(), None, artifacts=[], upstream=upstream)
    parsed = ReleaseReadinessOutput.model_validate(body)
    # Grounded: the blocking financial result drives FAIL and shows in evidence gaps.
    assert parsed.verdict == "FAIL"
    fin = [c for c in parsed.checklist if "Financial" in c.item]
    assert fin and fin[0].status == "INCOMPLETE"
    assert any("financial_data_integrity" in g for g in parsed.evidence_gaps)


def test_deployment_risk_grounded_no_go_on_blocker():
    from app.services.agents.output_schemas import DeploymentRiskOutput
    upstream = [
        _up("financial_data_integrity", "FAIL", blocking=True),
        _up("test_execution_analyst", "PASS"),
        _up("apex_coverage", "PASS", deployable=True, gate_passed=True),
    ]
    body = build("deployment_risk", _story("HIGH"), None, artifacts=[], upstream=upstream)
    parsed = DeploymentRiskOutput.model_validate(body)
    assert parsed.recommendation == "NO_GO" and parsed.verdict == "FAIL"
    assert any(f.status == "BLOCKER" and "Financial" in f.factor for f in parsed.factors)


def test_release_readiness_all_green():
    upstream = [_up(k, "PASS") for k in
                ("ac_compliance", "apex_coverage", "static_analysis",
                 "test_execution_analyst", "financial_data_integrity", "regression_scope")]
    body = build("release_readiness", _story(), None, artifacts=[], upstream=upstream)
    parsed = ReleaseReadinessOutput.model_validate(body)
    assert parsed.verdict == "PASS"
    assert all(c.status == "COMPLETE" for c in parsed.checklist)


def test_monitoring_hypercare_flags_missing():
    body = build("monitoring_hypercare", _story(), None, artifacts=[])
    parsed = MonitoringHypercareOutput.model_validate(body)
    assert parsed.dashboards and parsed.alerts and parsed.slos
    # Fixture intentionally has MISSING items -> WARN.
    assert parsed.verdict == "WARN"
    assert parsed.on_call and parsed.runbook_ready is True
    assert parsed.release_blocking is False
