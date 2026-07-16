"""Development-phase agents added to match the industry-standard QE set:
Automated Code Review and Deployability Validation. Both behave like the other
Development agents — artifact consumers, advisory, non-blocking.
"""

from app.models import AGENT_ARTIFACT_KINDS, ArtifactKind, Phase
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    OUTPUT_SCHEMAS,
    CodeReviewOutput,
    DeployabilityValidationOutput,
)
from app.services.agents.registry import agents_for_phase


def _story():
    class _S:
        jira_key = "WLTH-101"
        summary = "Household rollup recalculates client-facing balance"
        acceptance_criteria = ["Rollup sums active accounts"]
        fca_impact = None
        cloud = None

    return _S()


def _artifact(kind: str, parsed: dict) -> dict:
    return {"kind": kind, "filename": f"f.{kind.lower()}", "summary": "", "parsed": parsed}


SARIF = _artifact(
    "SARIF",
    {
        "findings": [
            {"rule": "AvoidSoqlInLoops", "level": "warning",
             "message": "SOQL in a loop", "location": "HouseholdRollupService.cls:142"},
            {"rule": "EmptyCatchBlock", "level": "error",
             "message": "Swallowed exception", "location": "Rollup.cls:88"},
        ],
        "counts": {"warning": 1, "error": 1},
    },
)
METADATA = _artifact("METADATA", {"components": [
    "ApexClass: HouseholdRollupService", "ApexTrigger: FinancialAccountTrigger",
]})
JUNIT_FAIL = _artifact("JUNIT", {
    "total": 3, "passed": 2, "failed": 1, "errors": 0, "skipped": 0,
    "failures": [{"name": "recalcBulk", "classname": "T", "status": "failed", "message": "SOQL 101"}],
    "all_tests": ["a", "b", "recalcBulk"],
})
JUNIT_PASS = _artifact("JUNIT", {
    "total": 3, "passed": 3, "failed": 0, "errors": 0, "skipped": 0,
    "failures": [], "all_tests": ["a", "b", "c"],
})


# ------------------------------------------------------------------ registry


def test_development_has_five_agents_in_order():
    seq = [a.key for a in agents_for_phase(Phase.DEVELOPMENT)]
    assert seq == [
        "ac_compliance",
        "apex_coverage",
        "static_analysis",
        "code_review",
        "deployability_validation",
    ]


def test_new_dev_agents_registered():
    for key in ("code_review", "deployability_validation"):
        assert key in OUTPUT_SCHEMAS and key in GENERATORS and key in AGENT_ARTIFACT_KINDS
    assert ArtifactKind.SARIF in AGENT_ARTIFACT_KINDS["code_review"]
    assert ArtifactKind.JUNIT in AGENT_ARTIFACT_KINDS["deployability_validation"]


# ------------------------------------------------------------------ code review


def test_code_review_from_sarif():
    body = build("code_review", _story(), None, artifacts=[SARIF, METADATA])
    parsed = CodeReviewOutput.model_validate(body)
    assert parsed.review_comments
    # An error-level scanner finding drives a REQUEST_CHANGES recommendation.
    assert parsed.approval_recommendation == "REQUEST_CHANGES"
    assert parsed.verdict == "FAIL"
    assert parsed.metrics.files_reviewed >= 1
    assert parsed.complexity_hotspots
    assert parsed.release_blocking is False


def test_code_review_clean_is_advisory_only():
    # No artifacts -> only the AI design/test comments (MEDIUM) -> COMMENT/WARN.
    body = build("code_review", _story(), None, artifacts=[])
    parsed = CodeReviewOutput.model_validate(body)
    assert parsed.approval_recommendation in ("COMMENT", "APPROVE")
    assert parsed.release_blocking is False


# ------------------------------------------------------------- deployability


def test_deployability_fails_on_test_failure():
    body = build("deployability_validation", _story(), None, artifacts=[METADATA, JUNIT_FAIL])
    parsed = DeployabilityValidationOutput.model_validate(body)
    assert parsed.deployable is False
    assert parsed.validation_status == "FAILED"
    assert parsed.verdict == "FAIL"
    assert parsed.component_errors and parsed.blockers
    assert parsed.release_blocking is False  # strong signal, but the gate is the control


def test_deployability_succeeds_when_clean():
    body = build("deployability_validation", _story(), None, artifacts=[METADATA, JUNIT_PASS])
    parsed = DeployabilityValidationOutput.model_validate(body)
    assert parsed.deployable is True
    assert parsed.validation_status == "SUCCEEDED"
    assert parsed.verdict == "PASS"
    assert parsed.components.total >= 1
    assert parsed.release_blocking is False


# ------------------------------------------------ v3 enrichment of existing 3


def test_static_analysis_v3_taxonomy_ratings_debt():
    from app.services.agents.output_schemas import StaticAnalysisOutput

    body = build("static_analysis", _story(), None, artifacts=[SARIF, METADATA])
    parsed = StaticAnalysisOutput.model_validate(body)
    # Every issue carries the SonarQube taxonomy + remediation effort.
    assert parsed.issues and all(i.effort_minutes > 0 for i in parsed.issues)
    tax = parsed.taxonomy
    assert (tax.bug + tax.vulnerability + tax.code_smell + tax.security_hotspot) == len(parsed.issues)
    assert parsed.ratings.reliability in ("A", "B", "C", "D", "E")
    assert parsed.ratings.security in ("A", "B", "C", "D", "E")
    assert "h" in parsed.technical_debt.effort  # e.g. "1h 40m"


def test_apex_coverage_v3_new_code_gate():
    from app.services.agents.output_schemas import ApexCoverageOutput

    body = build("apex_coverage", _story(), None, artifacts=[])
    parsed = ApexCoverageOutput.model_validate(body)
    assert parsed.new_code.target == 80.0
    assert parsed.new_code.changed_classes >= 1
    assert isinstance(parsed.gate_passed, bool)
    # Gate requires BOTH overall floor and new-code target.
    assert parsed.gate_passed == (parsed.deployable and parsed.new_code.meets_target)


def test_ac_compliance_v3_bidirectional_traceability():
    from app.services.agents.output_schemas import AcComplianceOutput

    body = build("ac_compliance", _story(), None, artifacts=[METADATA])
    parsed = AcComplianceOutput.model_validate(body)
    assert isinstance(parsed.traceability.score_percent, float)
    assert isinstance(parsed.traceability.gate_passed, bool)
    # No BDD upstream here -> a canned orphan test illustrates reverse traceability.
    assert parsed.traceability.orphan_tests
