from enum import Enum


class Phase(str, Enum):
    REFINEMENT = "REFINEMENT"
    DEVELOPMENT = "DEVELOPMENT"
    TESTING = "TESTING"
    RELEASE = "RELEASE"


PHASE_ORDER: list[Phase] = [
    Phase.REFINEMENT,
    Phase.DEVELOPMENT,
    Phase.TESTING,
    Phase.RELEASE,
]


def next_phase(phase: Phase) -> Phase | None:
    idx = PHASE_ORDER.index(phase)
    if idx + 1 < len(PHASE_ORDER):
        return PHASE_ORDER[idx + 1]
    return None


class Cloud(str, Enum):
    FSC = "FSC"
    SALES = "SALES"
    MARKETING = "MARKETING"


class FcaImpact(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ScopeStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class RunStatus(str, Enum):
    PROPOSED = "PROPOSED"                  # created; predecessor not yet accepted
    AWAITING_APPROVAL = "AWAITING_APPROVAL"  # unlocked; waiting for human Approve & Run
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"                # output ready; waiting for human decision
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RERUN_REQUESTED = "RERUN_REQUESTED"    # superseded by a child run
    FAILED = "FAILED"                      # engine/API error


class GateStatus(str, Enum):
    LOCKED = "LOCKED"
    READY_FOR_SIGNOFF = "READY_FOR_SIGNOFF"
    SIGNED_OFF = "SIGNED_OFF"
    REJECTED = "REJECTED"


class ArtifactKind(str, Enum):
    SARIF = "SARIF"            # static analysis (PMD/Copado, SARIF 2.1.0)
    JUNIT = "JUNIT"            # test results (JUnit/pytest/Playwright XML)
    COVERAGE = "COVERAGE"      # code/Apex coverage (JSON or Cobertura XML)
    METADATA = "METADATA"      # changed components / deployment manifest
    FINANCIAL = "FINANCIAL"    # expected-vs-actual validation data
    GENERIC = "GENERIC"        # freeform text, passed through as context


# Which agents consume which artifact kinds.
AGENT_ARTIFACT_KINDS: dict[str, list[ArtifactKind]] = {
    "ac_compliance": [ArtifactKind.METADATA],
    "apex_coverage": [ArtifactKind.COVERAGE, ArtifactKind.METADATA],
    "static_analysis": [ArtifactKind.SARIF, ArtifactKind.METADATA],
    "code_review": [ArtifactKind.SARIF, ArtifactKind.METADATA],
    "deployability_validation": [ArtifactKind.METADATA, ArtifactKind.JUNIT],
    "test_execution_analyst": [ArtifactKind.JUNIT],
    "financial_data_integrity": [ArtifactKind.FINANCIAL],
    "regression_scope": [ArtifactKind.METADATA],
    "integration_e2e_journey": [ArtifactKind.JUNIT, ArtifactKind.METADATA],
    "defect_triage": [ArtifactKind.JUNIT],
    "security_dast": [ArtifactKind.SARIF, ArtifactKind.METADATA],
    "test_data_management": [ArtifactKind.METADATA],
}

# Which agents consume the accepted output of upstream agents on the same
# story (chained pipeline: BDD formalizes the Three Amigos example map; AC
# Compliance cross-references BDD scenarios for test coverage per criterion).
AGENT_UPSTREAM_INPUTS: dict[str, list[str]] = {
    # Refinement regulatory chain (shift-left compliance):
    "fca_regulatory_impact": ["story_quality"],
    "consumer_duty_mapper": ["fca_regulatory_impact"],
    "compliance_ac_advisor": ["fca_regulatory_impact", "consumer_duty_mapper"],
    "bdd_generator": ["story_quality", "three_amigos", "compliance_ac_advisor"],
    "ac_compliance": ["bdd_generator"],
    "apex_coverage": ["bdd_generator"],
    "test_execution_analyst": ["bdd_generator"],
    "financial_data_integrity": ["bdd_generator"],
    "regression_scope": ["bdd_generator"],
    "integration_e2e_journey": ["bdd_generator", "regression_scope"],
    "defect_triage": ["test_execution_analyst"],
    "uat_test_design": ["bdd_generator", "compliance_ac_advisor"],
}


class PushType(str, Enum):
    COMMENT = "COMMENT"
    LABEL = "LABEL"
    TRANSITION = "TRANSITION"
    ATTACHMENT = "ATTACHMENT"


class PushStatus(str, Enum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
