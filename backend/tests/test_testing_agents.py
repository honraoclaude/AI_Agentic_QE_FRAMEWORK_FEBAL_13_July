"""Industry-standard Testing-phase agents: Integration & E2E Journey,
Defect Triage, Security (DAST), Test Data Management.
Advisory, non-blocking, appended at Testing seq 4-7.
"""

from app.models import Phase
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    OUTPUT_SCHEMAS,
    DefectTriageOutput,
    E2EJourneyOutput,
    SecurityDastOutput,
)
from app.services.agents.output_schemas import TestDataOutput as TDMOutput  # aliased: avoid pytest Test* collection
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


def _artifact(kind, parsed):
    return {"kind": kind, "filename": f"f.{kind.lower()}", "summary": "", "parsed": parsed}


SARIF = _artifact("SARIF", {"findings": [
    {"rule": "reflected-xss", "level": "warning", "message": "Reflected input", "location": "/s/search"},
], "counts": {"warning": 1}})
METADATA = _artifact("METADATA", {"components": ["ApexClass: HouseholdRollupService"]})
JUNIT_FAIL = _artifact("JUNIT", {
    "total": 3, "passed": 2, "failed": 1, "errors": 0, "skipped": 0,
    "failures": [{"name": "recalcUnderBulkLoad", "classname": "T", "status": "failed",
                  "message": "System.LimitException: Too many SOQL queries: 101"}],
    "all_tests": ["a", "b", "recalcUnderBulkLoad"],
})
JUNIT_PASS = _artifact("JUNIT", {
    "total": 3, "passed": 3, "failed": 0, "errors": 0, "skipped": 0, "failures": [], "all_tests": ["a", "b", "c"]})


def test_testing_phase_has_seven_agents_in_order():
    seq = [a.key for a in agents_for_phase(Phase.TESTING)]
    assert seq == [
        "test_execution_analyst", "financial_data_integrity", "regression_scope",
        "integration_e2e_journey", "defect_triage", "security_dast",
        "test_data_management",
    ]


def test_new_testing_agents_registered():
    for key in ("integration_e2e_journey", "defect_triage", "security_dast",
                "test_data_management"):
        assert key in OUTPUT_SCHEMAS and key in GENERATORS


def test_security_dast_flags_idor_and_fails():
    body = build("security_dast", _story(), None, artifacts=[SARIF, METADATA])
    parsed = SecurityDastOutput.model_validate(body)
    assert any("IDOR" in f.name or "Broken Access" in f.owasp for f in parsed.security_findings)
    assert parsed.risk_rating in ("CRITICAL", "HIGH")
    assert parsed.verdict == "FAIL"
    assert parsed.counts["high"] >= 1
    assert parsed.release_blocking is False


def test_defect_triage_clusters_and_suggests_defect():
    up = [{"agent_key": "test_execution_analyst", "agent_name": "TEA",
           "output": {"run_summary": {"failed": 1}}}]
    body = build("defect_triage", _story(), None, artifacts=[JUNIT_FAIL], upstream=up)
    parsed = DefectTriageOutput.model_validate(body)
    assert parsed.clusters and any(c.classification == "PRODUCT_DEFECT" for c in parsed.clusters)
    assert parsed.suggested_defects
    assert parsed.verdict == "FAIL"  # CRITICAL product defect
    assert parsed.release_blocking is False


def test_integration_e2e_journey_maps_clouds():
    body = build("integration_e2e_journey", _story(), None, artifacts=[JUNIT_PASS], upstream=[])
    parsed = E2EJourneyOutput.model_validate(body)
    assert parsed.journeys
    assert any("FSC" in j.clouds for j in parsed.journeys)
    assert parsed.total_integration_points >= 1
    assert parsed.release_blocking is False


def test_test_data_management_all_synthetic():
    body = build("test_data_management", _story(), None, artifacts=[METADATA])
    parsed = TDMOutput.model_validate(body)
    assert parsed.fixtures and parsed.all_synthetic is True
    assert parsed.pii_flags  # flagged for synthesis
    assert parsed.verdict == "PASS"
    assert parsed.release_blocking is False
