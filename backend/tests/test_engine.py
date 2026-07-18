import pytest
from sqlalchemy import select

from app.models import Story
from app.services import workflow
from app.services.agents import engine
from app.services.agents.output_schemas import (
    OUTPUT_SCHEMAS,
    ClassificationBreakdown,
    FailureAnalysis,
    Finding,
    FinancialIntegrityOutput,
    IntegrityCheck,
    Reconciliation,
    RunSummary,
    StoryQualityOutput,
    InvestScores,
    TestExecutionOutput,
)
from app.services.agents.prompts import (
    PromptNotFoundError,
    available_versions,
    load_prompt,
)
from app.services.agents.registry import AGENTS
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


# ------------------------------------------------------------ prompt registry


def test_every_agent_has_its_pinned_prompt_on_disk():
    for agent in AGENTS.values():
        text = load_prompt(agent.key, agent.prompt_version)
        assert len(text) > 300, f"{agent.key} prompt suspiciously short"
        assert agent.prompt_version in available_versions(agent.key)


def test_missing_prompt_raises_clearly():
    with pytest.raises(PromptNotFoundError):
        load_prompt("story_quality", "v999")
    with pytest.raises(PromptNotFoundError):
        load_prompt("no_such_agent", "v1")


def test_every_agent_has_an_output_schema():
    assert set(OUTPUT_SCHEMAS) == set(AGENTS)


# ----------------------------------------------------- demo-fixture fallback


async def test_no_api_key_uses_rich_demo_fixture(session, adapter):
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    result = await workflow.approve_and_run(session, run.id, approver="Test Lead")
    # Demo path is clearly labelled and produces full, schema-shaped output.
    assert result.model == "demo-fixture"
    out = result.output_json
    assert out["invest_scores"]["testable"] >= 1
    assert len(out["acceptance_criteria_gaps"]) >= 1
    assert out["agent"] == "story_quality"
    # The exact story context sent is captured for the Input view.
    assert result.input_json["story"]["jira_key"] == story.jira_key


async def test_run_records_the_prompt_version_that_actually_executed(session, adapter):
    """A run proposed before a prompt upgrade must not claim the old version
    after executing with the new one — the audit record reflects reality."""
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    run.prompt_version = "v0-stale"  # simulate: proposed before a registry bump
    await session.flush()

    result = await workflow.approve_and_run(session, run.id, approver="Test Lead")
    current = AGENTS["story_quality"].prompt_version
    assert result.prompt_version == current  # re-stamped at execution
    assert result.input_json["prompt_version"] == current  # row and input agree


async def test_demo_fixtures_cover_every_agent(session, adapter):
    from app.services.agents.demo_outputs import GENERATORS
    from app.services.agents.registry import AGENTS

    assert set(GENERATORS) == set(AGENTS)
    story = await _seed(session, adapter)
    for key in AGENTS:
        body = GENERATORS[key](story)
        assert body["verdict"] in ("PASS", "WARN", "FAIL")
        assert isinstance(body["summary"], str) and body["summary"]
        assert "release_blocking" in body
        # Demo fixtures must not accidentally block the happy path.
        assert body["release_blocking"] is False


async def test_three_amigos_v2_output_shape(session, adapter):
    """Tier-1 additions: Example Mapping, story-tailored DoD with compliance
    evidence, agreements log, and categorised risks."""
    from app.services.agents.demo_outputs import GENERATORS
    from app.services.agents.output_schemas import ThreeAmigosOutput

    story = await _seed(session, adapter)  # WLTH-101 is FCA HIGH
    body = GENERATORS["three_amigos"](story)

    # Validates against the v3 schema (structured cards, DoD, agreements, risks).
    parsed = ThreeAmigosOutput.model_validate(body)
    assert len(parsed.example_map) >= 2
    assert all(r.examples for r in parsed.example_map)
    assert parsed.agreements and parsed.open_questions
    assert any(r.category == "COMPLIANCE" for r in parsed.risks)
    # HIGH-impact story -> DoD carries explicit FCA evidence items, mapped to
    # the verifying agents (checkable contract, not prose).
    assert any(item.fca_evidence for item in parsed.definition_of_done)
    assert any(item.verified_by not in ("", "MANUAL")
               for item in parsed.definition_of_done)
    # No Gherkin here — that's the BDD agent's job.
    assert "scenarios" not in body


async def test_bdd_v3_classification_priority_automation(session, adapter):
    """v3: scenarios classified (category/test_type), prioritized, with a
    per-scenario automation recommendation and a coverage breakdown."""
    from app.services.agents.demo_outputs import GENERATORS, build
    from app.services.agents.output_schemas import BddGeneratorOutput

    story = await _seed(session, adapter)
    ta_output = GENERATORS["three_amigos"](story)
    upstream = [
        {"agent_key": "three_amigos", "agent_name": "Three Amigos", "output": ta_output}
    ]
    body = build("bdd_generator", story, None, artifacts=[], upstream=upstream)

    parsed = BddGeneratorOutput.model_validate(body)
    assert parsed.feature.name and parsed.feature.narrative.as_a

    # Every scenario is classified, prioritised and has an automation decision.
    cats = {s.category for s in parsed.scenarios}
    assert cats == {"POSITIVE", "NEGATIVE", "EDGE"}  # a real spread
    assert {s.priority for s in parsed.scenarios} <= {"P1", "P2", "P3"}
    assert all(s.automation and s.automation.reason for s in parsed.scenarios)
    assert any(not s.automation.recommended for s in parsed.scenarios)  # a manual one
    assert any(s.test_type == "NON_FUNCTIONAL" for s in parsed.scenarios)

    # Tags denormalize the classification for runner selection.
    for s in parsed.scenarios:
        assert f"@{s.category.lower()}" in s.tags
        assert f"@{s.priority.lower()}" in s.tags
        assert ("@automated" in s.tags) == s.automation.recommended
        assert ("@manual" in s.tags) != s.automation.recommended

    # Coverage breakdown reconciles with the scenarios.
    b = parsed.coverage.breakdown
    assert b.positive + b.negative + b.edge == len(parsed.scenarios)
    assert b.automatable + b.manual == len(parsed.scenarios)

    # Traceability preserved; no separate automation_hints field remains.
    rule_texts = {r["rule"] for r in ta_output["example_map"]}
    assert any(c in rule_texts for s in parsed.scenarios for c in s.covers)
    assert not hasattr(parsed, "automation_hints")
    assert parsed.test_data_requirements


async def test_ac_compliance_v2_rtm(session, adapter):
    """v2: requirements traceability matrix — status states, component + test
    traceability, scope creep, FCA/severity gaps, confidence."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import GENERATORS, build
    from app.services.agents.output_schemas import AcComplianceOutput

    story = await _seed(session, adapter)

    # No artifact -> NOT_VERIFIABLE with LOW confidence.
    body = build("ac_compliance", story, None, artifacts=[], upstream=[])
    parsed = AcComplianceOutput.model_validate(body)
    assert parsed.evidence_confidence == "LOW"
    assert all(m.status == "NOT_VERIFIABLE" for m in parsed.ac_mapping)

    # With a metadata manifest + upstream BDD -> real statuses, components, tests.
    meta = parsers.parse(
        ArtifactKind.METADATA,
        '["ApexClass: HouseholdRollupService","ApexTrigger: FinancialAccountTrigger",'
        '"ApexClass: AuditService","ApexClass: OrphanHelper"]',
    )
    artifacts = [
        {"kind": "METADATA", "filename": "package.json", "summary": meta["summary"], "parsed": meta["parsed"]}
    ]
    bdd_output = build(
        "bdd_generator",
        story,
        None,
        artifacts=[],
        upstream=[{"agent_key": "three_amigos", "agent_name": "TA", "output": GENERATORS["three_amigos"](story)}],
    )
    upstream = [{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd_output}]
    body = build("ac_compliance", story, None, artifacts=artifacts, upstream=upstream)
    parsed = AcComplianceOutput.model_validate(body)

    assert parsed.evidence_confidence == "HIGH"
    statuses = {m.status for m in parsed.ac_mapping}
    assert "COVERED" in statuses and ("NOT_COVERED" in statuses or "PARTIAL" in statuses)
    # Component traceability + coverage counts reconcile.
    assert any(m.components for m in parsed.ac_mapping)
    cov = parsed.coverage
    assert cov.covered + cov.partial + cov.not_covered + cov.not_verifiable == cov.total
    # Scope creep: the orphan component is flagged.
    assert any("Orphan" in u.component for u in parsed.unmapped_work)
    # Test coverage cross-referenced from the BDD scenarios.
    assert any(m.test_coverage.has_scenario for m in parsed.ac_mapping)
    # An FCA-relevant NOT_COVERED gap drives FAIL.
    fca_gap = any(
        m.status == "NOT_COVERED" and m.fca_relevant for m in parsed.ac_mapping
    )
    if fca_gap:
        assert body["verdict"] == "FAIL"


async def test_apex_coverage_v2(session, adapter):
    """v2: per-class threshold + deployability, assertion risk, structured gaps,
    financial weighting, drafted tests traced to gaps/BDD, projected delta."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import GENERATORS, build
    from app.services.agents.output_schemas import ApexCoverageOutput

    story = await _seed(session, adapter)

    # Coverage report with a financial class below the 85% policy.
    cov = parsers.parse(
        ArtifactKind.COVERAGE,
        '{"overall_percent": 80.0, "classes": ['
        '{"name":"HouseholdRollupService","coverage_percent":72.0},'
        '{"name":"AccountTriggerHandler","coverage_percent":88.0}]}',
    )
    artifacts = [
        {"kind": "COVERAGE", "filename": "cov.json", "summary": cov["summary"], "parsed": cov["parsed"]}
    ]
    bdd_output = build(
        "bdd_generator", story, None, artifacts=[],
        upstream=[{"agent_key": "three_amigos", "agent_name": "TA", "output": GENERATORS["three_amigos"](story)}],
    )
    upstream = [{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd_output}]
    body = build("apex_coverage", story, None, artifacts=artifacts, upstream=upstream)

    parsed = ApexCoverageOutput.model_validate(body)
    rollup = next(c for c in parsed.classes if c.class_name == "HouseholdRollupService")
    assert rollup.financial_critical and not rollup.meets_threshold
    assert rollup.assertion_risk == "HIGH"  # financial-critical → flagged
    assert rollup.gaps and any(g.risk == "HIGH" for g in rollup.gaps)
    # Deployability: overall 80% >= 75 floor but a financial class is below policy.
    assert parsed.deployable is True
    assert parsed.threshold_met is False
    assert body["verdict"] == "FAIL"  # financial class below policy
    # Projected coverage exceeds current after drafting tests.
    assert parsed.projected_coverage_percent >= parsed.overall_coverage_percent
    # Drafted tests trace to gaps; at least one links to a BDD Apex scenario.
    assert parsed.drafted_tests and all(t.closes_gaps for t in parsed.drafted_tests)
    assert any(t.from_bdd_scenario for t in parsed.drafted_tests)


async def test_static_analysis_v2_triage_and_gate(session, adapter):
    """v2: triage with suppressions, sourced+categorized issues, CWE mapping,
    quality gate driving the verdict."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import build
    from app.services.agents.output_schemas import StaticAnalysisOutput

    story = await _seed(session, adapter)

    # SARIF with a real finding + a naming-convention noise rule.
    sarif = parsers.parse(
        ArtifactKind.SARIF,
        '{"version":"2.1.0","runs":[{"results":['
        '{"ruleId":"ApexSharingViolations","level":"error",'
        '"message":{"text":"Missing with sharing"},'
        '"locations":[{"physicalLocation":{"artifactLocation":{"uri":"Rollup.cls"},"region":{"startLine":1}}}]},'
        '{"ruleId":"MethodNamingConventions","level":"note","message":{"text":"camelCase"}}]}]}',
    )
    artifacts = [
        {"kind": "SARIF", "filename": "scan.sarif", "summary": sarif["summary"], "parsed": sarif["parsed"]}
    ]
    body = build("static_analysis", story, None, artifacts=artifacts, upstream=[])
    parsed = StaticAnalysisOutput.model_validate(body)

    # Triage: the naming rule is suppressed as noise, real finding confirmed.
    assert parsed.triage.raw_findings == 2
    assert parsed.triage.suppressed == 1
    assert any("Naming" in s.reason or "naming" in s.reason for s in parsed.suppressed)
    assert parsed.triage.added_by_ai >= 1  # FSC review adds findings

    # Both sources present; AI findings are fsc_specific.
    sources = {i.source for i in parsed.issues}
    assert sources == {"SCANNER", "AI_AUGMENT"}
    assert any(i.source == "AI_AUGMENT" and i.fsc_specific for i in parsed.issues)

    # Categories + CWE mapping on the sharing/security issues.
    assert any(i.category == "FINANCIAL_ACCURACY" for i in parsed.issues)
    sharing = [i for i in parsed.issues if i.category == "SHARING_VISIBILITY"]
    assert sharing and sharing[0].standard and sharing[0].standard.cwe == "CWE-284"
    assert all(i.remediation for i in parsed.issues)

    # Quality gate fails on HIGH issues -> verdict FAIL, counts reconcile.
    assert parsed.quality_gate.passed is False
    assert body["verdict"] == "FAIL"
    assert parsed.counts.blocking_count == parsed.counts.critical + parsed.counts.high


async def test_financial_integrity_v2_tolerance_and_not_validated(session, adapter):
    """v2: categorized checks with variance/tolerance/materiality, reconciliation,
    and un-validated financial criteria blocking the release."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import build
    from app.services.agents.output_schemas import FinancialIntegrityOutput as FIO

    story = await _seed(session, adapter)  # WLTH-101 has rounding + reconciliation AC

    # Financial file covers the rollup (a near-miss within no tolerance) but NOT
    # the rounding or reconciliation criteria.
    fin = parsers.parse(
        ArtifactKind.FINANCIAL,
        '[{"name":"Household rollup total","expected":"875000.00","actual":"875000.00"}]',
    )
    artifacts = [{"kind": "FINANCIAL", "filename": "recon.json", "summary": fin["summary"], "parsed": fin["parsed"]}]
    body = build("financial_data_integrity", story, None, artifacts=artifacts, upstream=[])
    parsed = FIO.model_validate(body)

    rollup = parsed.checks[0]
    assert rollup.category == "ROLLUP" and rollup.regulatory_basis
    assert rollup.tolerance == "0.00" and rollup.within_tolerance is True
    # Reconciliation counts reconcile with the checks.
    assert parsed.reconciliation.total == len(parsed.checks)
    # Financial AC (e.g. rounding) not covered by a check -> un-validated -> blocks.
    assert parsed.not_validated
    assert body["release_blocking"] is True and body["verdict"] == "FAIL"


async def test_financial_integrity_v2_within_tolerance_passes(session, adapter):
    """A rounding near-miss within the 0.01 tolerance still passes."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import build
    from app.services.agents.output_schemas import FinancialIntegrityOutput as FIO

    story = await _seed(session, adapter)
    # Cover every financial AC so not_validated is empty; rounding is within 0.01.
    fin = parsers.parse(
        ArtifactKind.FINANCIAL,
        '[{"name":"Household rollup sums active accounts","expected":"875000.00","actual":"875000.00"},'
        '{"name":"Closed and pending accounts excluded","expected":"excluded","actual":"excluded"},'
        '{"name":"Rollup recalculates GBP rounding","expected":"1250.00","actual":"1250.005"},'
        '{"name":"Values display GBP rounding 2dp","expected":"1250.00","actual":"1250.005"}]',
    )
    artifacts = [{"kind": "FINANCIAL", "filename": "recon.json", "summary": fin["summary"], "parsed": fin["parsed"]}]
    body = build("financial_data_integrity", story, None, artifacts=artifacts, upstream=[])
    parsed = FIO.model_validate(body)
    rounding = [c for c in parsed.checks if c.category == "ROUNDING"]
    assert rounding and rounding[0].within_tolerance is True and rounding[0].passed is True


async def test_regression_scope_v2(session, adapter):
    """v2: areas with driving components, dependency type, effort, BDD suites,
    plus explicit exclusions and a summary."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import GENERATORS, build
    from app.services.agents.output_schemas import RegressionScopeOutput

    story = await _seed(session, adapter)
    meta = parsers.parse(
        ArtifactKind.METADATA,
        '["ApexClass: HouseholdRollupService","ApexTrigger: FinancialAccountTrigger"]',
    )
    artifacts = [{"kind": "METADATA", "filename": "pkg.json", "summary": meta["summary"], "parsed": meta["parsed"]}]
    bdd_output = build(
        "bdd_generator", story, None, artifacts=[],
        upstream=[{"agent_key": "three_amigos", "agent_name": "TA", "output": GENERATORS["three_amigos"](story)}],
    )
    upstream = [{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd_output}]
    body = build("regression_scope", story, None, artifacts=artifacts, upstream=upstream)
    parsed = RegressionScopeOutput.model_validate(body)

    assert parsed.recommended_areas and parsed.excluded
    fsc = next(a for a in parsed.recommended_areas if a.cloud == "FSC")
    assert fsc.driving_components and fsc.dependency_type and fsc.effort
    assert fsc.suggested_tests  # mapped to BDD scenarios/tags
    assert parsed.scope_summary.high >= 1 and "FSC" in parsed.scope_summary.clouds
    assert body["release_blocking"] is False


async def test_apex_coverage_not_deployable_below_floor(session, adapter):
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import build
    from app.services.agents.output_schemas import ApexCoverageOutput

    story = await _seed(session, adapter)
    cov = parsers.parse(
        ArtifactKind.COVERAGE,
        '{"overall_percent": 68.0, "classes": [{"name":"UtilityHelper","coverage_percent":68.0}]}',
    )
    artifacts = [{"kind": "COVERAGE", "filename": "c.json", "summary": cov["summary"], "parsed": cov["parsed"]}]
    body = build("apex_coverage", story, None, artifacts=artifacts, upstream=[])
    parsed = ApexCoverageOutput.model_validate(body)
    assert parsed.deployable is False  # below the 75% platform floor
    assert body["verdict"] == "FAIL"


async def test_upstream_gathering_feeds_bdd(session, adapter):
    """End-to-end: accepting the Refinement chain makes the upstream outputs BDD
    declares (Story Quality, Three Amigos, Compliance-by-Design AC Advisor)
    available via the workflow's upstream gathering."""
    story = await _seed(session, adapter)
    # Walk every Refinement agent up to (but not including) BDD, in sequence.
    for key in (
        "story_quality",
        "fca_regulatory_impact",
        "consumer_duty_mapper",
        "compliance_ac_advisor",
        "three_amigos",
    ):
        run = await workflow.latest_run(session, story.id, key)
        await workflow.approve_and_run(session, run.id, approver="QE Lead")
        await workflow.accept_run(session, run.id, actor="QE Lead")

    gathered = await workflow._gather_upstream(session, story.id, "bdd_generator")
    keys = {u["agent_key"] for u in gathered}
    assert keys == {"story_quality", "three_amigos", "compliance_ac_advisor"}

    bdd = await workflow.latest_run(session, story.id, "bdd_generator")
    result = await workflow.approve_and_run(session, bdd.id, approver="QE Lead")
    # The run records which upstream agents it consumed.
    up = {u["agent_key"] for u in result.input_json["upstream"]}
    assert up == {"story_quality", "three_amigos", "compliance_ac_advisor"}
    # And its scenarios trace to the Three Amigos rules.
    assert result.output_json["coverage"]["rules_total"] >= 1


# ----------------------------------------------------- real path (mocked API)


def _fake_story_quality() -> StoryQualityOutput:
    return StoryQualityOutput(
        verdict="WARN",
        summary="Solid story; two AC gaps around rounding evidence.",
        findings=[
            Finding(
                title="No rounding AC",
                detail="Rollup rounding behaviour is unspecified for GBP.",
                severity="MEDIUM",
            )
        ],
        release_blocking=False,
        invest_scores=InvestScores(
            independent=4, negotiable=4, valuable=5, estimable=4, small=3, testable=4
        ),
        fca_compliance_notes="Consumer Duty relevant: client-facing net worth figure.",
        proposed_fca_impact=None,
        proposed_cloud=None,
        acceptance_criteria_gaps=[
            "Rollup value is rounded half-up to 2 decimal places",
            "An audit record is written when the rollup recalculates",
        ],
    )


async def test_real_path_uses_prompt_model_and_schema(
    session, adapter, isolated_settings, monkeypatch
):
    isolated_settings.anthropic_api_key = "test-key"
    captured = {}

    async def fake_call(model, system_prompt, user_text, schema):
        captured.update(
            model=model, system=system_prompt, user=user_text, schema=schema
        )
        return _fake_story_quality(), {"input_tokens": 1234, "output_tokens": 567}

    monkeypatch.setattr(engine, "_call_claude", fake_call)

    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    result = await workflow.approve_and_run(session, run.id, approver="Test Lead")

    # Model + prompt + schema routing.
    assert captured["model"] == isolated_settings.reasoning_model
    assert captured["schema"] is StoryQualityOutput
    assert "INVEST" in captured["system"]  # versioned prompt file content
    assert "WLTH-101" in captured["user"]  # story context injected

    # Envelope + schema fields persisted; usage + hashes recorded for audit.
    out = result.output_json
    assert out["agent"] == "story_quality"
    assert out["pact"] == ["Proactive", "Targeted"]
    assert out["invest_scores"]["testable"] == 4
    assert out["acceptance_criteria_gaps"][0].startswith("Rollup value")
    assert result.model == isolated_settings.reasoning_model
    assert result.token_usage == {"input_tokens": 1234, "output_tokens": 567}
    assert result.output_hash and result.input_hash


async def test_rerun_guidance_is_injected_into_prompt(
    session, adapter, isolated_settings, monkeypatch
):
    isolated_settings.anthropic_api_key = "test-key"
    captured_users = []

    async def fake_call(model, system_prompt, user_text, schema):
        captured_users.append(user_text)
        return _fake_story_quality(), {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(engine, "_call_claude", fake_call)

    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    child = await workflow.request_rerun(
        session, run.id, actor="Test Lead", guidance="Score Consumer Duty explicitly"
    )
    await workflow.approve_and_run(session, child.id, approver="Test Lead")

    assert "<reviewer_guidance>" not in captured_users[0]
    assert "Score Consumer Duty explicitly" in captured_users[1]
    assert "re-run attempt 2" in captured_users[1]


async def test_financial_blocking_enforced_server_side_even_if_model_disagrees(
    session, adapter, isolated_settings, monkeypatch
):
    """The model returns release_blocking=False despite a failed check —
    the engine must force True/FAIL. No prompt or model output can un-block."""
    isolated_settings.anthropic_api_key = "test-key"

    async def fake_call(model, system_prompt, user_text, schema):
        if schema is FinancialIntegrityOutput:
            return (
                FinancialIntegrityOutput(
                    verdict="PASS",  # deliberately wrong
                    summary="All fine, honest.",
                    findings=[],
                    release_blocking=False,  # deliberately wrong
                    checks=[
                        IntegrityCheck(
                            name="household rollup",
                            category="ROLLUP",
                            expected="1250000.00",
                            actual="1249998.37",
                            variance="1.63",
                            tolerance="0.00",
                            within_tolerance=False,
                            passed=False,
                            materiality="£1.63 on rollup",
                            severity="BLOCKER",
                        )
                    ],
                    reconciliation=Reconciliation(
                        total=1, passed=0, failed=1, within_tolerance=0, total_variance="1.63"
                    ),
                    not_validated=[],
                ),
                {"input_tokens": 1, "output_tokens": 1},
            )
        return _fake_story_quality(), {"input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr(engine, "_call_claude", fake_call)

    story = await _seed(session, adapter)
    # Jump straight to executing the financial agent by proposing its run
    # manually via the registry sequence: walk phases quickly on the stub-free
    # fake — simpler: call engine.execute directly on a synthetic run.
    run = await workflow.latest_run(session, story.id, "story_quality")
    fin_agent = AGENTS["financial_data_integrity"]
    result = await engine.execute(run, story, fin_agent)
    assert result["output"]["release_blocking"] is True
    assert result["output"]["verdict"] == "FAIL"


async def test_fca_scenario_failure_enforced_server_side(
    session, adapter, isolated_settings, monkeypatch
):
    isolated_settings.anthropic_api_key = "test-key"

    def _run_summary():
        return RunSummary(total=1, passed=0, failed=1, errors=0, skipped=0, pass_rate=0.0)

    async def fake_call(model, system_prompt, user_text, schema):
        return (
            TestExecutionOutput(
                verdict="WARN",
                summary="One failure.",
                findings=[],
                release_blocking=False,  # deliberately wrong
                run_summary=_run_summary(),
                failures=[
                    FailureAnalysis(
                        test_name="[FCA] suitability record stored immutably",
                        classification="PRODUCT_DEFECT",
                        severity="BLOCKER",
                        priority="P1",
                        is_fca_scenario=True,
                        likely_flaky=False,
                        rerun_recommended=False,
                        detail="Record was editable after submission.",
                        suggested_action="Raise a defect.",
                    )
                ],
                classification_breakdown=ClassificationBreakdown(
                    product_defect=1, test_defect=0, environment=0, data=0,
                    fca_failures=1, blocking=1,
                ),
                unexecuted_fca_scenarios=[],
                failure_groups=[],
            ),
            {"input_tokens": 1, "output_tokens": 1},
        )

    monkeypatch.setattr(engine, "_call_claude", fake_call)

    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    result = await engine.execute(run, story, AGENTS["test_execution_analyst"])
    assert result["output"]["release_blocking"] is True
    assert result["output"]["verdict"] == "FAIL"


async def test_test_execution_v2_triage_and_unexecuted_fca_blocks(session, adapter):
    """v2: run summary, classification with severity/action, BDD grounding of
    is_fca_scenario, and un-executed FCA scenarios blocking the release."""
    from app.models import ArtifactKind
    from app.services.artifacts import parsers
    from app.services.agents.demo_outputs import GENERATORS, build
    from app.services.agents.output_schemas import TestExecutionOutput as TEO

    story = await _seed(session, adapter)
    bdd_output = build(
        "bdd_generator", story, None, artifacts=[],
        upstream=[{"agent_key": "three_amigos", "agent_name": "TA", "output": GENERATORS["three_amigos"](story)}],
    )
    upstream = [{"agent_key": "bdd_generator", "agent_name": "BDD", "output": bdd_output}]

    # JUnit: a locator failure and a sandbox timeout — NO audit test (the only
    # @fca BDD scenario) was executed.
    junit = parsers.parse(
        ArtifactKind.JUNIT,
        "<testsuites><testsuite>"
        '<testcase name="rollup sums accounts"/>'
        '<testcase name="household tile renders"><failure message="locator not found"/></testcase>'
        '<testcase name="recalc under load"><failure message="sandbox timeout"/></testcase>'
        "</testsuite></testsuites>",
    )
    artifacts = [
        {"kind": "JUNIT", "filename": "results.xml", "summary": junit["summary"], "parsed": junit["parsed"]}
    ]
    body = build("test_execution_analyst", story, None, artifacts=artifacts, upstream=upstream)
    # Server-side enforcement runs through the engine on the real path; the demo
    # sets release_blocking itself — validate the shape and blocking here.
    parsed = TEO.model_validate(body)

    assert parsed.run_summary.total == 3 and parsed.run_summary.failed == 2
    classifications = {f.classification for f in parsed.failures}
    assert "TEST_DEFECT" in classifications and "ENVIRONMENT" in classifications
    # Flaky/env failure recommends a re-run, not a defect.
    env = next(f for f in parsed.failures if f.classification == "ENVIRONMENT")
    assert env.rerun_recommended and env.suggested_defect is None
    # The @fca "immutable audit record" scenario never ran -> flagged + blocks.
    assert parsed.unexecuted_fca_scenarios
    assert body["release_blocking"] is True and body["verdict"] == "FAIL"
    # A product defect suggests a Jira defect.
    prod = [f for f in parsed.failures if f.classification == "PRODUCT_DEFECT"]
    assert all(p.suggested_defect for p in prod) if prod else True


async def test_api_failure_marks_run_failed_not_lost(
    session, adapter, isolated_settings, monkeypatch
):
    isolated_settings.anthropic_api_key = "test-key"

    async def exploding_call(model, system_prompt, user_text, schema):
        raise RuntimeError("simulated API outage")

    monkeypatch.setattr(engine, "_call_claude", exploding_call)

    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    result = await workflow.approve_and_run(session, run.id, approver="Test Lead")
    assert result.status.value == "FAILED"
    assert "simulated API outage" in result.decision_reason
    # Recoverable: a re-run with guidance is allowed from FAILED.
    child = await workflow.request_rerun(
        session, run.id, actor="Test Lead", guidance="retry"
    )
    assert child.attempt == 2
