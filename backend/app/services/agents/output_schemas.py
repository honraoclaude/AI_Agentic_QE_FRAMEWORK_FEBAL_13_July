"""Structured JSON output schema per agent (Pydantic models).

Passed to the Claude API as structured outputs, so agent responses are
guaranteed valid against the schema — no fragile JSON parsing. All agents
share a common envelope (verdict / summary / findings / release_blocking)
that the workflow and UI rely on; agent-specific fields extend it.
"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


class Finding(BaseModel):
    title: str
    detail: str
    severity: Severity


class AgentOutputBase(BaseModel):
    verdict: Literal["PASS", "WARN", "FAIL"]
    summary: str = Field(description="2-5 sentence executive summary of the result")
    findings: list[Finding]
    release_blocking: bool = Field(
        description="True only for hard-blocking failures (FCA scenarios, "
        "financial data integrity). Enforced server-side regardless."
    )


# --- Phase 1: Refinement -------------------------------------------------


class InvestScores(BaseModel):
    independent: int = Field(ge=1, le=5)
    negotiable: int = Field(ge=1, le=5)
    valuable: int = Field(ge=1, le=5)
    estimable: int = Field(ge=1, le=5)
    small: int = Field(ge=1, le=5)
    testable: int = Field(ge=1, le=5)


class StoryQualityOutput(AgentOutputBase):
    invest_scores: InvestScores
    fca_compliance_notes: str
    proposed_fca_impact: Literal["LOW", "MEDIUM", "HIGH"] | None = Field(
        description="Only when the story has no FCA impact set; a human confirms"
    )
    proposed_cloud: Literal["FSC", "SALES", "MARKETING"] | None
    acceptance_criteria_gaps: list[str] = Field(
        description="Missing AC written as candidate acceptance-criteria lines"
    )


# --- Refinement: regulatory agents (shift-left compliance) ---------------


class ApplicableRegulation(BaseModel):
    handbook_ref: str = Field(description='e.g. "COBS 9.2", "PRIN 2A" (Consumer Duty)')
    area: Literal["COBS", "PRIN", "PROD", "SYSC", "DISP", "SMCR", "ICOBS", "SUP"]
    obligation: str = Field(description="The specific obligation this story must meet")
    relevance: str = Field(description="Why this regulation applies to this story")


class FcaRegulatoryImpactOutput(AgentOutputBase):
    """Cited FCA Handbook mapping + a reasoned FCA-impact proposal (a human
    confirms; does not auto-write the story)."""

    proposed_fca_impact: Literal["LOW", "MEDIUM", "HIGH"]
    impact_rationale: str
    applicable_regulations: list[ApplicableRegulation]
    key_risks: list[Finding] = Field(
        description="Regulatory risks if the obligations are not met"
    )


ConsumerDutyOutcome = Literal[
    "PRODUCTS_AND_SERVICES",
    "PRICE_AND_VALUE",
    "CONSUMER_UNDERSTANDING",
    "CONSUMER_SUPPORT",
]
OutcomeStatus = Literal["ADDRESSED", "PARTIAL", "NOT_ADDRESSED", "NOT_APPLICABLE"]


class ConsumerDutyAssessment(BaseModel):
    outcome: ConsumerDutyOutcome
    status: OutcomeStatus
    assessment: str
    foreseeable_harm: str | None = Field(
        default=None, description="Foreseeable harm to (vulnerable) customers, if any"
    )
    gap: str | None = Field(
        default=None, description="What is missing to fully address the outcome"
    )


class ConsumerDutyOutput(AgentOutputBase):
    outcomes: list[ConsumerDutyAssessment] = Field(
        description="All four Consumer Duty outcomes, each assessed"
    )
    unaddressed_count: int
    cross_cutting_notes: str = Field(
        description="Act in good faith / avoid foreseeable harm / enable financial objectives"
    )


AcCategory = Literal[
    "AUDIT",
    "SUITABILITY",
    "DISCLOSURE",
    "CONSENT",
    "VULNERABLE_CUSTOMER",
    "RECORD_KEEPING",
    "ACCESS_CONTROL",
    "DATA_INTEGRITY",
]


class SuggestedCriterion(BaseModel):
    criterion: str = Field(description="A concrete, testable acceptance-criterion line")
    category: AcCategory
    regulatory_basis: str = Field(description='Handbook / Consumer Duty basis, e.g. "SYSC 9.1"')
    priority: Literal["MUST", "RECOMMENDED"]


class ComplianceAcAdvisorOutput(AgentOutputBase):
    """Turns regulatory obligations into concrete acceptance criteria before
    Three Amigos / BDD formalise them."""

    suggested_criteria: list[SuggestedCriterion]
    coverage_gaps: list[str] = Field(
        description="Obligations with no matching existing acceptance criterion"
    )


class PersonaPrompts(BaseModel):
    product_owner: list[str]
    developer: list[str]
    quality_engineer: list[str]


class ExampleRule(BaseModel):
    """An Example Mapping pairing: one testable business rule (blue card) with
    the concrete examples that illustrate it (green cards)."""

    rule: str = Field(description="A single testable business rule")
    examples: list[str] = Field(
        description="Concrete examples/cases (happy, negative, boundary) for this rule"
    )


class Risk(BaseModel):
    risk: str
    category: Literal["DELIVERY", "TECHNICAL", "COMPLIANCE", "DATA"]
    mitigation: str


class ThreeAmigosOutput(AgentOutputBase):
    # Example Mapping is the structured core — rules + examples feed the BDD
    # Scenario Generator (this agent deliberately does NOT emit Gherkin).
    example_map: list[ExampleRule] = Field(
        description="Business rules each with concrete examples; the raw material "
        "the BDD Scenario Generator turns into Gherkin"
    )
    definition_of_done: list[str] = Field(
        description="Story-tailored Definition of Done, including explicit FCA "
        "compliance-evidence items to capture"
    )
    agreements: list[str] = Field(
        description="Decisions the three amigos explicitly agreed — auditable "
        "resolutions, distinct from open questions"
    )
    risks: list[Risk]
    open_questions: list[str] = Field(
        description="Unresolved questions blocking full shared understanding"
    )
    persona_prompts: PersonaPrompts
    refinement_summary: str


class FeatureNarrative(BaseModel):
    as_a: str
    i_want: str
    so_that: str


class Feature(BaseModel):
    name: str
    narrative: FeatureNarrative
    background: list[str] = Field(
        default_factory=list, description="Shared Given steps common to all scenarios"
    )


class ScenarioAutomation(BaseModel):
    recommended: bool = Field(description="Should this scenario be automated?")
    framework: Literal[
        "Apex", "Copado Robotic Testing", "Playwright", "pytest", "Manual"
    ] = Field(description="Automation framework, or 'Manual' when not automated")
    suggested_method: str | None = Field(
        default=None, description="Suggested test-method name when automated"
    )
    reason: str = Field(description="Why automate this, or why it stays manual")


class BddScenario(BaseModel):
    title: str
    level: Literal["unit", "api", "ui"]
    # Two orthogonal axes: the case path, and the aspect under test.
    category: Literal["POSITIVE", "NEGATIVE", "EDGE"] = Field(
        description="POSITIVE (happy path), NEGATIVE (invalid/error), EDGE (boundary)"
    )
    test_type: Literal["FUNCTIONAL", "NON_FUNCTIONAL"] = Field(
        description="FUNCTIONAL behaviour vs a NON_FUNCTIONAL requirement (perf/security)"
    )
    priority: Literal["P1", "P2", "P3"] = Field(
        description="P1 regulatory/financial/critical, P2 core, P3 edge/cosmetic"
    )
    automation: ScenarioAutomation
    tags: list[str] = Field(
        description="Denormalized Gherkin tags for runner selection — include level, "
        "category, type, priority, automation, and @fca/@smoke/@regression"
    )
    covers: list[str] = Field(
        description="Rule(s)/acceptance-criteria this scenario satisfies — traceability"
    )
    gherkin: str = Field(description="Complete well-formed Gherkin scenario")


class TestBreakdown(BaseModel):
    positive: int
    negative: int
    edge: int
    functional: int
    non_functional: int
    automatable: int
    manual: int


class BddCoverage(BaseModel):
    rules_total: int
    rules_covered: int
    ac_covered: int
    uncovered: list[str] = Field(
        description="Rules/AC with no scenario yet — Gate 1 gaps"
    )
    breakdown: TestBreakdown = Field(
        description="Counts of scenarios by category, type and automation status"
    )


class BddPyramid(BaseModel):
    unit: int
    api: int
    ui: int
    target: str = Field(description="e.g. '60/20/20'")
    within_target: bool
    note: str


class BddGeneratorOutput(AgentOutputBase):
    feature: Feature
    scenarios: list[BddScenario]
    coverage: BddCoverage
    pyramid: BddPyramid
    test_data_requirements: list[str]


# --- Phase 2: Development ------------------------------------------------


class AcTestCoverage(BaseModel):
    has_scenario: bool = Field(description="Is this criterion covered by a BDD scenario?")
    scenarios: list[str] = Field(description="Titles of covering scenarios, if any")


class AcMappingItem(BaseModel):
    criterion: str
    status: Literal["COVERED", "PARTIAL", "NOT_COVERED", "NOT_VERIFIABLE"] = Field(
        description="COVERED (evidence exists), PARTIAL (some), NOT_COVERED (gap), "
        "NOT_VERIFIABLE (no artifact to judge)"
    )
    components: list[str] = Field(
        description="Changed metadata components that implement this criterion"
    )
    evidence: str
    fca_relevant: bool = Field(
        description="Does this criterion carry a regulatory/FCA obligation?"
    )
    severity: Literal["NONE", "LOW", "MEDIUM", "HIGH"] = Field(
        description="Severity of the gap; NONE when COVERED"
    )
    test_coverage: AcTestCoverage
    remediation: str = Field(description="Action to close the gap; empty when COVERED")


class UnmappedWork(BaseModel):
    component: str
    concern: str = Field(description="Why this change maps to no acceptance criterion")


class AcCoverage(BaseModel):
    total: int
    covered: int
    partial: int
    not_covered: int
    not_verifiable: int
    ac_covered_percent: float


class AcComplianceOutput(AgentOutputBase):
    ac_mapping: list[AcMappingItem]
    unmapped_work: list[UnmappedWork] = Field(
        description="Changed work mapping to no acceptance criterion (scope creep)"
    )
    coverage: AcCoverage
    confidence: Literal["HIGH", "LOW"] = Field(
        description="HIGH when real change artifacts were analysed, LOW when inferred"
    )


class ApexGap(BaseModel):
    type: Literal["BULK", "NEGATIVE", "EXCEPTION", "SHARING_CRUD", "BRANCH"]
    area: str = Field(description="The method/branch/path that is uncovered")
    risk: Literal["LOW", "MEDIUM", "HIGH"]


class ApexClassCoverage(BaseModel):
    class_name: str
    coverage_percent: float
    covered_lines: int | None = None
    total_lines: int | None = None
    meets_threshold: bool = Field(description="Meets the 85% per-class org policy")
    financial_critical: bool = Field(
        description="Handles financial calculation / regulatory logic"
    )
    assertion_risk: Literal["NONE", "LOW", "HIGH"] = Field(
        description="Risk that coverage exists without meaningful assertions"
    )
    has_bulk_test: bool
    has_negative_test: bool
    gaps: list[ApexGap]


class ApexThreshold(BaseModel):
    per_class_target: float = Field(description="Org policy per-class target, e.g. 85")
    platform_floor: float = Field(description="Salesforce deploy floor, 75")


class DraftedTest(BaseModel):
    test_class_name: str
    test_method: str
    category: Literal["POSITIVE", "NEGATIVE", "BULK", "EXCEPTION"]
    priority: Literal["P1", "P2", "P3"]
    closes_gaps: list[str] = Field(description="Which coverage gaps this test closes")
    from_bdd_scenario: str | None = Field(
        default=None, description="The BDD scenario this test realizes, if any"
    )
    outline: str
    test_data: str = Field(description="TestDataFactory fixtures the test needs")


class ApexCoverageOutput(AgentOutputBase):
    classes: list[ApexClassCoverage]
    overall_coverage_percent: float
    projected_coverage_percent: float = Field(
        description="Projected overall coverage if the drafted tests are implemented"
    )
    threshold: ApexThreshold
    threshold_met: bool
    deployable: bool = Field(
        description="Would the Copado/SFDX deploy pass (overall >= platform floor)?"
    )
    drafted_tests: list[DraftedTest]


IssueCategory = Literal[
    "SECURITY",
    "SHARING_VISIBILITY",
    "FINANCIAL_ACCURACY",
    "PERFORMANCE",
    "AUDITABILITY",
    "MAINTAINABILITY",
]


class StaticStandard(BaseModel):
    cwe: str = Field(description="CWE identifier, e.g. CWE-284")
    owasp: str = Field(description="OWASP category, e.g. A01:2021 Broken Access Control")


class StaticIssue(BaseModel):
    rule: str
    severity: Severity
    category: IssueCategory
    source: Literal["SCANNER", "AI_AUGMENT"] = Field(
        description="SCANNER (from the SARIF scan) vs AI_AUGMENT (FSC review the "
        "scanner cannot do)"
    )
    location: str
    detail: str
    remediation: str = Field(description="The concrete fix")
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="Certainty / false-positive risk"
    )
    fsc_specific: bool
    standard: StaticStandard | None = Field(
        default=None, description="CWE/OWASP mapping for security issues"
    )


class SuppressedFinding(BaseModel):
    rule: str
    location: str
    reason: str = Field(description="Why this scanner finding was discarded as noise")


class TriageSummary(BaseModel):
    raw_findings: int
    confirmed: int
    added_by_ai: int
    suppressed: int


class StaticCounts(BaseModel):
    critical: int
    high: int
    medium: int
    low: int
    security: int
    financial_accuracy: int
    sharing_visibility: int
    performance: int
    auditability: int
    maintainability: int
    blocking_count: int = Field(description="CRITICAL + HIGH")


class QualityGateCondition(BaseModel):
    name: str
    threshold: str
    actual: str
    status: Literal["PASS", "FAIL"]


class QualityGate(BaseModel):
    conditions: list[QualityGateCondition]
    passed: bool


class StaticAnalysisOutput(AgentOutputBase):
    issues: list[StaticIssue]
    suppressed: list[SuppressedFinding]
    triage: TriageSummary
    counts: StaticCounts
    quality_gate: QualityGate


# --- Development: Automated Code Review ----------------------------------


class ReviewComment(BaseModel):
    file: str
    line: int | None = None
    category: Literal[
        "COMPLEXITY",
        "NAMING",
        "DUPLICATION",
        "BEST_PRACTICE",
        "DESIGN",
        "ERROR_HANDLING",
        "READABILITY",
        "TEST_DESIGN",
    ]
    severity: Severity
    comment: str
    suggestion: str


class CodeMetrics(BaseModel):
    files_reviewed: int
    max_cyclomatic_complexity: int
    avg_method_lines: int
    duplication_percent: float


class ComplexityHotspot(BaseModel):
    unit: str = Field(description="Class.method or component")
    complexity: int
    recommendation: str


class CodeReviewOutput(AgentOutputBase):
    approval_recommendation: Literal["APPROVE", "COMMENT", "REQUEST_CHANGES"]
    metrics: CodeMetrics
    review_comments: list[ReviewComment]
    complexity_hotspots: list[ComplexityHotspot]


# --- Development: Deployability Validation (validate-only deploy) ---------


class DeployComponents(BaseModel):
    total: int
    deployed: int
    failed: int


class ComponentError(BaseModel):
    component: str
    component_type: str
    problem: str
    line: int | None = None


class DeployTestRun(BaseModel):
    total: int
    passed: int
    failed: int


class DeployabilityValidationOutput(AgentOutputBase):
    deployable: bool
    validation_status: Literal["SUCCEEDED", "FAILED", "PARTIAL"]
    target_env: str
    components: DeployComponents
    component_errors: list[ComponentError]
    test_run: DeployTestRun | None = None
    blockers: list[str] = Field(
        description="Concrete reasons the package cannot deploy as-is"
    )


# --- Phase 3: Testing ----------------------------------------------------


TestSeverity = Literal["BLOCKER", "CRITICAL", "MAJOR", "MINOR"]


class RunSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    pass_rate: float


class SuggestedDefect(BaseModel):
    title: str
    component: str
    severity: TestSeverity


class FailureAnalysis(BaseModel):
    test_name: str
    classification: Literal["PRODUCT_DEFECT", "TEST_DEFECT", "ENVIRONMENT", "DATA"]
    severity: TestSeverity
    priority: Literal["P1", "P2", "P3"]
    is_fca_scenario: bool
    bdd_scenario: str | None = Field(
        default=None, description="The BDD scenario this test maps to, if matched"
    )
    likely_flaky: bool
    rerun_recommended: bool
    detail: str
    suggested_action: str = Field(description="The concrete next step for triage")
    suggested_defect: SuggestedDefect | None = Field(
        default=None, description="A Jira defect to raise, for product defects"
    )


class ClassificationBreakdown(BaseModel):
    product_defect: int
    test_defect: int
    environment: int
    data: int
    fca_failures: int
    blocking: int


class FailureGroup(BaseModel):
    cause: str
    tests: list[str]


class TestExecutionOutput(AgentOutputBase):
    __test__ = False  # not a pytest class, despite the name

    run_summary: RunSummary
    failures: list[FailureAnalysis]
    classification_breakdown: ClassificationBreakdown
    unexecuted_fca_scenarios: list[str] = Field(
        description="@fca BDD scenarios with no executed test — missing evidence"
    )
    failure_groups: list[FailureGroup] = Field(
        description="Failures clustered by a shared root cause"
    )


class IntegrityCheck(BaseModel):
    name: str
    category: Literal[
        "ROLLUP", "FEE", "PRORATION", "ROUNDING", "EXCLUSION", "HOUSEHOLDING", "RECONCILIATION"
    ]
    expected: str
    actual: str = Field(description="Observed value, or NOT_EXECUTED")
    variance: str = Field(description="Numeric difference expected−actual, or N/A")
    tolerance: str = Field(description="Allowed variance, e.g. 0.00 or 0.01")
    within_tolerance: bool
    passed: bool
    materiality: str = Field(description="The financial (£) impact of any discrepancy")
    severity: Literal["BLOCKER", "CRITICAL", "MAJOR", "MINOR"]
    regulatory_basis: str | None = Field(
        default=None, description="The FCA obligation this evidences (COBS/Consumer Duty/CASS)"
    )
    source: str | None = Field(default=None, description="Data source / lineage")


class Reconciliation(BaseModel):
    total: int
    passed: int
    failed: int
    within_tolerance: int
    total_variance: str


class FinancialIntegrityOutput(AgentOutputBase):
    checks: list[IntegrityCheck]
    reconciliation: Reconciliation
    not_validated: list[str] = Field(
        description="Financial criteria with no check — missing evidence, blocking"
    )


class RegressionArea(BaseModel):
    cloud: Literal["FSC", "SALES", "MARKETING"]
    area: str
    driving_components: list[str] = Field(
        description="Changed components that put this area at risk"
    )
    dependency_type: Literal[
        "SHARED_OBJECT", "AUTOMATION", "INTEGRATION", "SHARING_CONFIG", "ROLLUP_CONFIG"
    ]
    reason: str
    priority: Literal["LOW", "MEDIUM", "HIGH"]
    effort: str = Field(description="Rough size, e.g. '~12 test cases, 2h'")
    suggested_tests: list[str] = Field(
        description="Concrete BDD scenarios / tags to run for this area"
    )


class ExcludedArea(BaseModel):
    area: str
    reason: str = Field(description="Why this area is safely out of regression scope")


class RegressionSummary(BaseModel):
    high: int
    medium: int
    low: int
    clouds: list[str]
    total_effort: str


class RegressionScopeOutput(AgentOutputBase):
    recommended_areas: list[RegressionArea]
    excluded: list[ExcludedArea]
    scope_summary: RegressionSummary


# --- Phase 4: Release ----------------------------------------------------


class ChecklistItem(BaseModel):
    item: str
    status: Literal["COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"]
    notes: str


class ReleaseReadinessOutput(AgentOutputBase):
    checklist: list[ChecklistItem]
    evidence_gaps: list[str]


class RequiredApproval(BaseModel):
    role: str
    required_because: str


class UatSignoffOutput(AgentOutputBase):
    required_approvals: list[RequiredApproval]
    coordination_notes: str


class AuditReportSection(BaseModel):
    section: str
    content: str


class RegulatoryAuditOutput(AgentOutputBase):
    report_sections: list[AuditReportSection]
    completeness_confirmed: bool


OUTPUT_SCHEMAS: dict[str, type[AgentOutputBase]] = {
    "story_quality": StoryQualityOutput,
    "fca_regulatory_impact": FcaRegulatoryImpactOutput,
    "consumer_duty_mapper": ConsumerDutyOutput,
    "compliance_ac_advisor": ComplianceAcAdvisorOutput,
    "three_amigos": ThreeAmigosOutput,
    "bdd_generator": BddGeneratorOutput,
    "ac_compliance": AcComplianceOutput,
    "apex_coverage": ApexCoverageOutput,
    "static_analysis": StaticAnalysisOutput,
    "code_review": CodeReviewOutput,
    "deployability_validation": DeployabilityValidationOutput,
    "test_execution_analyst": TestExecutionOutput,
    "financial_data_integrity": FinancialIntegrityOutput,
    "regression_scope": RegressionScopeOutput,
    "release_readiness": ReleaseReadinessOutput,
    "uat_signoff_coordinator": UatSignoffOutput,
    "regulatory_audit_trail": RegulatoryAuditOutput,
}
