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
            key="three_amigos",
            name="Three Amigos Facilitation Agent",
            phase=Phase.REFINEMENT,
            sequence=2,
            pact=("Collaborative",),
            purpose=(
                "Builds shared understanding via Example Mapping (rules + "
                "examples), a story-tailored Definition of Done with FCA "
                "compliance evidence, an agreements log, risks, and open "
                "questions per persona. Feeds the BDD Scenario Generator."
            ),
            prompt_version="v2",
        ),
        AgentDefinition(
            key="bdd_generator",
            name="BDD Scenario Generator",
            phase=Phase.REFINEMENT,
            sequence=3,
            pact=("Autonomous", "Targeted"),
            purpose=(
                "Formalizes the Three Amigos example map into a commit-ready "
                ".feature file: positive/negative/edge scenarios classified by "
                "type and priority, per-scenario automation recommendations, "
                "rule/AC traceability, and a coverage matrix (Gate 1 evidence)."
            ),
            prompt_version="v3",
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
                "NOT_VERIFIABLE states, FCA/severity-weighted gaps, and scope-creep "
                "detection."
            ),
            prompt_version="v2",
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
                "sharing), financial-critical weighting, and drafted tests traced to "
                "gaps and BDD scenarios with a projected coverage delta."
            ),
            prompt_version="v2",
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
                "remediation, feeding a deterministic quality gate."
            ),
            prompt_version="v2",
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
        # --- Phase 4: Release ---
        AgentDefinition(
            key="release_readiness",
            name="Release Readiness Agent",
            phase=Phase.RELEASE,
            sequence=1,
            pact=("Collaborative",),
            purpose=(
                "Compiles the evidence pack: gate history, coverage, defect "
                "status, FCA scenario results."
            ),
        ),
        AgentDefinition(
            key="uat_signoff_coordinator",
            name="UAT Sign-Off Coordinator",
            phase=Phase.RELEASE,
            sequence=2,
            pact=("Collaborative",),
            purpose=(
                "Tracks required approvals: PO + Business stakeholder always; "
                "+ Compliance Officer when FCA impact = HIGH."
            ),
        ),
        AgentDefinition(
            key="regulatory_audit_trail",
            name="Regulatory Audit Trail Agent",
            phase=Phase.RELEASE,
            sequence=3,
            pact=("Proactive",),
            purpose=(
                "Generates the immutable release audit report (who approved "
                "what, when, with what evidence)."
            ),
        ),
    ]
}


def agents_for_phase(phase: Phase) -> list[AgentDefinition]:
    return sorted(
        (a for a in AGENTS.values() if a.phase == phase), key=lambda a: a.sequence
    )


def get_agent(key: str) -> AgentDefinition:
    return AGENTS[key]
