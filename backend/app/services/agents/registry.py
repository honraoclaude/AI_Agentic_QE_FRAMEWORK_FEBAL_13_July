"""The v1 agent roster. Pluggable: adding an agent = adding a definition here
plus a prompt file under backend/prompts/<key>/v<N>.md (Step 3).

Each agent declares its PACT classification, phase, execution order, model
tier, and whether its findings can block a release (FCA scenarios and
Financial Data Integrity are always release-blocking — no override).
"""

from dataclasses import dataclass, field

from ...models.enums import Phase


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    name: str
    phase: Phase
    sequence: int
    pact: tuple[str, ...]
    purpose: str
    model_role: str = "reasoning"  # "reasoning" | "classification"
    blocking_capable: bool = False  # may emit release_blocking findings
    prompt_version: str = "v1"


AGENTS: dict[str, AgentDefinition] = {
    a.key: a
    for a in [
        # --- Phase 1: Refinement ---
        AgentDefinition(
            key="story_quality",
            name="Story Quality Agent (INVEST + FCA)",
            phase=Phase.REFINEMENT,
            sequence=1,
            pact=("Proactive", "Targeted"),
            purpose=(
                "Scores the story against INVEST criteria plus an FCA Compliance "
                "dimension (COBS, Consumer Duty); flags acceptance-criteria gaps; "
                "proposes FCA-impact and Cloud values when Jira lacks them."
            ),
        ),
        AgentDefinition(
            key="fca_regulatory_impact",
            name="FCA Regulatory Impact Assessor",
            phase=Phase.REFINEMENT,
            sequence=2,
            pact=("Proactive", "Targeted"),
            purpose=(
                "Maps the story to the applicable FCA Handbook obligations "
                "(COBS, PRIN/Consumer Duty, PROD, SYSC, DISP, SM&CR) with citations, "
                "and proposes a reasoned FCA-impact rating for a human to confirm. "
                "Seeds the regulatory signal the rest of the pipeline builds on."
            ),
        ),
        AgentDefinition(
            key="consumer_duty_mapper",
            name="Consumer Duty Outcome Mapper",
            phase=Phase.REFINEMENT,
            sequence=3,
            pact=("Proactive",),
            purpose=(
                "Assesses the story against the four Consumer Duty outcomes "
                "(products & services, price & value, consumer understanding, "
                "consumer support), applying the avoid-foreseeable-harm lens, and "
                "flags which outcomes are unaddressed."
            ),
        ),
        AgentDefinition(
            key="compliance_ac_advisor",
            name="Compliance-by-Design AC Advisor",
            phase=Phase.REFINEMENT,
            sequence=4,
            pact=("Proactive", "Collaborative"),
            purpose=(
                "Turns the regulatory obligations and Consumer Duty gaps into "
                "concrete, testable acceptance criteria (audit, suitability, "
                "disclosure, consent, vulnerable-customer, record-keeping) — so "
                "compliance enters the ACs before Three Amigos and BDD formalise them."
            ),
        ),
        AgentDefinition(
            key="three_amigos",
            name="Three Amigos Facilitation Agent",
            phase=Phase.REFINEMENT,
            sequence=5,
            pact=("Collaborative",),
            purpose=(
                "Builds shared understanding via Example Mapping (AC-anchored "
                "rules + typed example cards) over the augmented AC set — "
                "consuming Story Quality's AC gaps and the Compliance AC "
                "Advisor's proposed criteria — with a verifiable DoD, "
                "decision-record agreements, risks, and owned open questions "
                "(blocking-aware). Feeds the BDD Scenario Generator."
            ),
            prompt_version="v5",
        ),
        AgentDefinition(
            key="bdd_generator",
            name="BDD Scenario Generator",
            phase=Phase.REFINEMENT,
            sequence=6,
            pact=("Autonomous", "Targeted"),
            purpose=(
                "Formalizes the Three Amigos example map into a commit-ready "
                ".feature file: positive/negative/edge scenarios classified by "
                "type and priority, per-scenario automation recommendations, "
                "rule/AC/example-card traceability with a deterministic "
                "every-example-covered check, and a coverage matrix (Gate 1 "
                "evidence)."
            ),
            prompt_version="v4",
        ),
        # --- Phase 2: Development ---
        AgentDefinition(
            key="ac_compliance",
            name="AC Compliance Checker",
            phase=Phase.DEVELOPMENT,
            sequence=1,
            pact=("Targeted",),
            purpose=(
                "Builds a requirements traceability matrix: each acceptance "
                "criterion linked to the components that implement it and the BDD "
                "scenarios that test it, with COVERED/PARTIAL/NOT_COVERED/"
                "NOT_VERIFIABLE states, FCA/severity-weighted gaps, scope-creep "
                "detection, and bidirectional traceability (orphan tests + score)."
            ),
            prompt_version="v3",
        ),
        AgentDefinition(
            key="apex_coverage",
            name="Apex Test Coverage Agent",
            phase=Phase.DEVELOPMENT,
            sequence=2,
            pact=("Autonomous",),
            purpose=(
                "Per-class coverage vs the 85% policy and 75% deploy floor, with "
                "assertion-quality risk, structured gaps (bulk/negative/exception/"
                "sharing), financial-critical weighting, coverage-on-new-code gate, "
                "and drafted tests traced to gaps and BDD scenarios."
            ),
            prompt_version="v3",
        ),
        AgentDefinition(
            key="static_analysis",
            name="Static Analysis Augment Agent",
            phase=Phase.DEVELOPMENT,
            sequence=3,
            pact=("Proactive",),
            purpose=(
                "Triages PMD/Copado SARIF output (dedupe + suppress noise) and adds "
                "FSC-specific security/quality findings the scanner can't — each "
                "categorized, sourced (scanner vs AI), CWE/OWASP-mapped, with "
                "remediation, an issue taxonomy, A–E ratings and technical-debt "
                "estimate, feeding a deterministic quality gate."
            ),
            prompt_version="v3",
        ),
        AgentDefinition(
            key="code_review",
            name="Automated Code Review Agent",
            phase=Phase.DEVELOPMENT,
            sequence=4,
            pact=("Autonomous", "Collaborative"),
            purpose=(
                "Automated peer review: complexity and maintainability metrics, "
                "categorised review comments with concrete suggestions (grounded in "
                "the actual changed source pulled from the branch — SOQL-in-loop, "
                "sharing), complexity hotspots, and an APPROVE / COMMENT / "
                "REQUEST_CHANGES recommendation — the standards layer above static analysis."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="deployability_validation",
            name="Deployability Validation Agent",
            phase=Phase.DEVELOPMENT,
            sequence=5,
            pact=("Proactive", "Targeted"),
            purpose=(
                "Validate-only deployment check: does the change set compile and "
                "deploy to the target org? Reports component-level errors, the "
                "validation test run, and a clear deployable / not-deployable verdict "
                "with blockers — the build gate before promotion."
            ),
        ),
        # --- Phase 3: Testing ---
        AgentDefinition(
            key="test_execution_analyst",
            name="Test Execution Analyst",
            phase=Phase.TESTING,
            sequence=1,
            pact=("Autonomous", "Targeted"),
            purpose=(
                "Triages test-run results into a report: run summary, failures "
                "classified with severity/priority/flakiness and suggested actions, "
                "grounded against BDD @fca scenarios. Open FCA-scenario failures — "
                "and un-executed FCA scenarios — are release-blocking."
            ),
            blocking_capable=True,
            prompt_version="v2",
        ),
        AgentDefinition(
            key="financial_data_integrity",
            name="Financial Data Integrity Agent",
            phase=Phase.TESTING,
            sequence=2,
            pact=("Proactive",),
            purpose=(
                "Validates FSC financial calculations against expected results with "
                "tolerance, materiality and regulatory basis per check, and a "
                "reconciliation summary. Any failed check — or any un-validated "
                "financial criterion — is release-blocking."
            ),
            blocking_capable=True,
            prompt_version="v2",
        ),
        AgentDefinition(
            key="regression_scope",
            name="Regression Scope Agent",
            phase=Phase.TESTING,
            sequence=3,
            pact=("Targeted",),
            purpose=(
                "Recommends a targeted regression suite across FSC/Sales/Marketing: "
                "each area traced to the changed components and dependency type, with "
                "effort, concrete BDD test suites, and explicit exclusions."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="integration_e2e_journey",
            name="Integration & E2E Journey Agent",
            phase=Phase.TESTING,
            sequence=4,
            pact=("Targeted", "Collaborative"),
            purpose=(
                "Validates the end-to-end journeys that span FSC, Sales and "
                "Marketing Cloud — the integration seams where cross-cloud defects "
                "hide — with per-journey status, risk and integration-point coverage."
            ),
        ),
        AgentDefinition(
            key="defect_triage",
            name="Defect Triage & Root-Cause Agent",
            phase=Phase.TESTING,
            sequence=5,
            pact=("Autonomous",),
            purpose=(
                "Clusters test failures by signature, classifies each "
                "(product/test/environment/data/flaky), hypothesises a root cause and "
                "suspected component, and drafts Jira defects with severity — turning "
                "'what failed' into 'why, and what next'."
            ),
        ),
        AgentDefinition(
            key="security_dast",
            name="Security Testing (DAST) Agent",
            phase=Phase.TESTING,
            sequence=6,
            pact=("Proactive",),
            purpose=(
                "Triages dynamic application security testing (OWASP ZAP / Burp / "
                "pen-test) findings against the running app and client portals — the "
                "runtime complement to Dev-phase SAST — each OWASP/CWE-mapped with a "
                "risk rating and remediation."
            ),
        ),
        AgentDefinition(
            key="test_data_management",
            name="Test Data Management Agent",
            phase=Phase.TESTING,
            sequence=7,
            pact=("Proactive", "Targeted"),
            purpose=(
                "Specifies the compliant test-data fixtures a story needs — synthetic "
                "or masked household/account data — and flags any field that would "
                "carry client PII if real data were used, so no real client data "
                "enters testing (FCA / UK GDPR)."
            ),
        ),
        # --- Phase 4: Release ---
        AgentDefinition(
            key="release_readiness",
            name="Release Readiness Agent",
            phase=Phase.RELEASE,
            sequence=1,
            pact=("Collaborative",),
            purpose=(
                "Compiles the readiness checklist grounded in the actual accepted "
                "results of the Development & Testing agents — coverage, defects, "
                "FCA-scenario and financial outcomes — with the evidence gaps."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="uat_signoff_coordinator",
            name="Business Sign-Off Coordinator",
            phase=Phase.RELEASE,
            sequence=2,
            pact=("Collaborative",),
            purpose=(
                "Coordinates the business demo sign-off: tracks the required "
                "approvers — PO + Business stakeholder always; + Compliance Officer "
                "when the assessed FCA impact = HIGH."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="regulatory_audit_trail",
            name="Regulatory Audit Trail Agent",
            phase=Phase.RELEASE,
            sequence=3,
            pact=("Proactive",),
            purpose=(
                "Generates the immutable release audit report grounded in the actual "
                "accepted results (who approved what, with what evidence; the real "
                "FCA / financial / security outcomes)."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="deployment_risk",
            name="Deployment Risk & Go/No-Go Assessor",
            phase=Phase.RELEASE,
            sequence=4,
            pact=("Proactive", "Targeted"),
            purpose=(
                "Aggregates gate results, coverage, open defects and change "
                "blast-radius into a risk-scored GO / CONDITIONAL_GO / NO_GO "
                "recommendation with the specific risk factors and any conditions — "
                "each factor grounded in an actual accepted agent result."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="change_management",
            name="Change Management & CAB Readiness Agent",
            phase=Phase.RELEASE,
            sequence=5,
            pact=("Collaborative",),
            purpose=(
                "Assembles the ITIL change record for the CAB: change type, risk "
                "category (grounded in the actual accepted results), affected "
                "services, proposed window with change-freeze check, and the approver "
                "matrix — the formal change-control layer above the sign-off."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="post_deploy_verification",
            name="Post-Deployment Verification Agent",
            phase=Phase.RELEASE,
            sequence=6,
            pact=("Autonomous", "Targeted"),
            purpose=(
                "Defines the production smoke tests and health checks to run "
                "immediately after deploy, with go-live and abort (rollback) "
                "criteria — the 'did it actually work in prod' check."
            ),
        ),
        AgentDefinition(
            key="release_notes",
            name="Release Notes & Change Documentation Agent",
            phase=Phase.RELEASE,
            sequence=7,
            pact=("Autonomous",),
            purpose=(
                "Generates the release notes / change record from the story, "
                "delivered acceptance criteria and changed components — grouped by "
                "change type, with known issues."
            ),
        ),
        AgentDefinition(
            key="monitoring_hypercare",
            name="Post-Release Monitoring & Hypercare Agent",
            phase=Phase.RELEASE,
            sequence=8,
            pact=("Proactive",),
            purpose=(
                "Confirms the dashboards, alerts/SLOs and support runbook are in "
                "place before go-live — with alerts/SLOs targeted at what the "
                "pipeline actually flagged — and defines the hypercare window and "
                "on-call, so the release is observable and supportable from minute one."
            ),
            prompt_version="v2",
        ),
    ]
}


def agents_for_phase(phase: Phase) -> list[AgentDefinition]:
    return sorted(
        (a for a in AGENTS.values() if a.phase == phase), key=lambda a: a.sequence
    )


def get_agent(key: str) -> AgentDefinition:
    return AGENTS[key]
