"""Rich, deterministic demo output per agent.

Used on the no-API-key path so demo mode showcases the full product — each
agent returns realistic, schema-shaped, story-tailored structured data that
the frontend renders properly formatted. This is NOT a Claude call; runs
produced this way are labelled model="demo-fixture" in the audit trail.

When real CI/CD artifacts are uploaded (SARIF, test results, coverage,
financial validation, changed metadata), the consuming agents derive their
output from that actual data — including release-blocking financial failures.
Without artifacts, they fall back to canned, story-tailored fixtures.

Every generator returns the agent-specific fields plus the shared envelope
(verdict / summary / findings / release_blocking). The engine wraps these
with agent identity and re-applies the server-side blocking rules.
"""

from ...models import AGENT_UPSTREAM_INPUTS, Story


def _ac(story: Story) -> list[str]:
    return story.acceptance_criteria or ["(no acceptance criteria captured)"]


def _fca(story: Story) -> str:
    return story.fca_impact.value if story.fca_impact else "HIGH (unconfirmed)"


def _cloud(story: Story) -> str:
    return story.cloud.value if story.cloud else "FSC"


def _parsed(artifacts: list[dict] | None, kind: str) -> dict | None:
    """Return the parsed content of the newest artifact of `kind`, if any."""
    for a in artifacts or []:
        if a.get("kind") == kind:
            return a.get("parsed") or {}
    return None


def _artifact_note(artifacts: list[dict] | None, kind: str) -> str:
    for a in artifacts or []:
        if a.get("kind") == kind:
            return f" (from uploaded artifact “{a.get('filename')}”)"
    return ""


def _upstream_output(upstream: list[dict] | None, agent_key: str) -> dict | None:
    for u in upstream or []:
        if u.get("agent_key") == agent_key:
            return u.get("output") or {}
    return None


# --- Phase 1: Refinement (no artifact consumers) -------------------------


def story_quality(story: Story, artifacts=None) -> dict:
    gaps = [
        "Rounding rule for GBP monetary values is explicit (half-up, 2 dp)",
        "An audit record is written whenever a client-facing figure recalculates",
    ]
    return {
        "verdict": "WARN",
        "summary": (
            f"{story.jira_key} is well-formed and valuable, but two acceptance-"
            "criteria gaps must close before it is estimable and testable: "
            "monetary rounding behaviour and record-keeping evidence."
        ),
        "findings": [
            {
                "title": "Rounding behaviour unspecified",
                "detail": "Monetary display and calculation rounding is not stated; "
                "COBS/Consumer Duty require a client-facing figure to be exact.",
                "severity": "MEDIUM",
            },
            {
                "title": "No auditability criterion",
                "detail": "No AC evidences that regulatory-relevant recalculations "
                "are recorded — needed for the 7-year audit trail.",
                "severity": "MEDIUM",
            },
        ],
        "release_blocking": False,
        "invest_scores": {
            "independent": 4,
            "negotiable": 4,
            "valuable": 5,
            "estimable": 3,
            "small": 3,
            "testable": 3,
        },
        "fca_compliance_notes": (
            f"FCA impact assessed {_fca(story)}. Consumer Duty relevant: the story "
            "produces a client-facing financial figure, so accuracy and evidencing "
            "are in scope. Confirm COBS record-keeping obligations with Compliance."
        ),
        "proposed_fca_impact": None if story.fca_impact else "HIGH",
        "proposed_cloud": None if story.cloud else "FSC",
        "acceptance_criteria_gaps": gaps,
    }


def fca_regulatory_impact(story: Story, artifacts=None, upstream=None) -> dict:
    impact = _fca(story).split()[0]  # LOW / MEDIUM / HIGH (drop "(unconfirmed)")
    if impact not in ("LOW", "MEDIUM", "HIGH"):
        impact = "HIGH"
    return {
        "verdict": "WARN",
        "summary": (
            f"{story.jira_key} engages client-facing financial figures on "
            f"{_cloud(story)}, so it sits within Consumer Duty and COBS "
            "record-keeping. Proposed FCA impact "
            f"{impact} — confirm at the Refinement gate."
        ),
        "findings": [
            {
                "title": "Client-facing figure accuracy in scope",
                "detail": "PRIN 2A (Consumer Duty) requires client-facing figures to "
                "be accurate and not cause foreseeable harm.",
                "severity": "MEDIUM",
            }
        ],
        "release_blocking": False,
        "proposed_fca_impact": impact,
        "impact_rationale": (
            "The story recalculates a value shown to clients and touches financial "
            "record-keeping; inaccuracy would risk a poor Consumer Duty outcome and "
            "a COBS record-keeping breach — hence a material impact rating."
        ),
        "applicable_regulations": [
            {
                "handbook_ref": "PRIN 2A",
                "area": "PRIN",
                "obligation": "Deliver good outcomes for retail clients (Consumer Duty).",
                "relevance": "The change alters a figure clients rely on.",
            },
            {
                "handbook_ref": "COBS 9.2",
                "area": "COBS",
                "obligation": "Maintain suitability and adequate records of client-facing outputs.",
                "relevance": "Recalculated figures must be evidenced and reproducible.",
            },
            {
                "handbook_ref": "SYSC 9.1",
                "area": "SYSC",
                "obligation": "Keep orderly records sufficient to reconstruct decisions.",
                "relevance": "Supports the 7-year audit trail for recalculations.",
            },
        ],
        "key_risks": [
            {
                "title": "Unevidenced recalculation",
                "detail": "Without an audit record, a challenged figure cannot be "
                "reconstructed — a SYSC 9 / Consumer Duty exposure.",
                "severity": "HIGH",
            }
        ],
    }


def consumer_duty_mapper(story: Story, artifacts=None, upstream=None) -> dict:
    impact = _upstream_output(upstream, "fca_regulatory_impact") or {}
    basis = (
        " Building on the regulatory impact assessment"
        if impact
        else ""
    )
    outcomes = [
        {
            "outcome": "PRODUCTS_AND_SERVICES",
            "status": "ADDRESSED",
            "assessment": "The rollup serves the intended target market (households).",
            "foreseeable_harm": None,
            "gap": None,
        },
        {
            "outcome": "PRICE_AND_VALUE",
            "status": "NOT_APPLICABLE",
            "assessment": "No fee or pricing change in this story.",
            "foreseeable_harm": None,
            "gap": None,
        },
        {
            "outcome": "CONSUMER_UNDERSTANDING",
            "status": "PARTIAL",
            "assessment": "The recalculated figure is shown to clients, but rounding "
            "and 'as-at' timing are not yet specified.",
            "foreseeable_harm": "A client could misread an ambiguous or stale figure.",
            "gap": "State rounding (half-up, 2dp) and the effective date shown.",
        },
        {
            "outcome": "CONSUMER_SUPPORT",
            "status": "NOT_ADDRESSED",
            "assessment": "No criterion covers how a client queries or disputes the figure.",
            "foreseeable_harm": "A vulnerable client may be unable to resolve a disputed value.",
            "gap": "Add a support/dispute path and an audit record for challenges.",
        },
    ]
    unaddressed = sum(1 for o in outcomes if o["status"] == "NOT_ADDRESSED")
    return {
        "verdict": "WARN",
        "summary": (
            f"{story.jira_key}: two of four Consumer Duty outcomes need work "
            "(consumer understanding, consumer support)." + basis + "."
        ),
        "findings": [
            {
                "title": "Consumer support path missing",
                "detail": "No AC covers querying/disputing a client-facing figure — a "
                "foreseeable-harm risk for vulnerable customers.",
                "severity": "MEDIUM",
            }
        ],
        "release_blocking": False,
        "outcomes": outcomes,
        "unaddressed_count": unaddressed,
        "cross_cutting_notes": (
            "Act in good faith and avoid foreseeable harm: an inaccurate or "
            "unexplained figure, or an unresolvable dispute, would breach the "
            "cross-cutting obligations. Enable clients to pursue their objectives by "
            "making the figure clear, timely and challengeable."
        ),
    }


def compliance_ac_advisor(story: Story, artifacts=None, upstream=None) -> dict:
    duty = _upstream_output(upstream, "consumer_duty_mapper") or {}
    gaps_from_duty = [
        o["gap"] for o in (duty.get("outcomes") or []) if o.get("gap")
    ]
    suggested = [
        {
            "criterion": "Every recalculation of a client-facing figure writes an "
            "immutable audit record (who/what/when/inputs).",
            "category": "AUDIT",
            "regulatory_basis": "SYSC 9.1",
            "priority": "MUST",
        },
        {
            "criterion": "Monetary values are rounded half-up to 2 decimal places and "
            "displayed with the effective 'as-at' date.",
            "category": "DISCLOSURE",
            "regulatory_basis": "PRIN 2A (Consumer Understanding)",
            "priority": "MUST",
        },
        {
            "criterion": "A client can raise a query on a displayed figure, and the "
            "query is logged with an auditable response path.",
            "category": "VULNERABLE_CUSTOMER",
            "regulatory_basis": "PRIN 2A (Consumer Support)",
            "priority": "MUST",
        },
        {
            "criterion": "Only users with the appropriate permission set can trigger a "
            "recalculation.",
            "category": "ACCESS_CONTROL",
            "regulatory_basis": "SYSC 3.2",
            "priority": "RECOMMENDED",
        },
    ]
    must = [c for c in suggested if c["priority"] == "MUST"]
    coverage_gaps = gaps_from_duty or [
        "No existing AC evidences record-keeping for recalculations.",
        "No existing AC covers a client dispute/support path.",
    ]
    return {
        "verdict": "WARN",
        "summary": (
            f"{len(suggested)} compliance acceptance criteria proposed for "
            f"{story.jira_key} ({len(must)} MUST). Adopt before Three Amigos so BDD "
            "can formalise them as @fca scenarios."
        ),
        "findings": [
            {
                "title": f"{len(must)} MUST-have compliance criteria missing",
                "detail": "Audit record, rounding/disclosure, and a consumer-support "
                "path are required for a compliant, testable story.",
                "severity": "MEDIUM",
            }
        ],
        "release_blocking": False,
        "suggested_criteria": suggested,
        "coverage_gaps": coverage_gaps,
    }


def three_amigos(story: Story, artifacts=None) -> dict:
    cloud = _cloud(story)
    high = story.fca_impact is None or story.fca_impact.value in ("MEDIUM", "HIGH")
    dod = [
        "All Example Mapping examples covered by approved BDD scenarios",
        "Apex/unit coverage meets the 85% org policy with meaningful assertions",
        "Code reviewed and static analysis clean of HIGH/CRITICAL issues",
        "Deployed through the Copado pipeline to UAT",
        "Story documentation / runbook updated where behaviour changed",
    ]
    if high:
        dod = [
            "Reconciliation vs finance extract attached (0.00 variance)",
            "[FCA] scenarios executed and evidence captured for Gate 3",
            "Immutable audit record for recalculation verified",
        ] + dod
    return {
        "verdict": "PASS",
        "summary": (
            f"Shared understanding captured for {story.jira_key} via Example "
            "Mapping. Two decisions agreed; one open question on pending-account "
            "treatment remains before BDD drafting."
        ),
        "findings": [],
        "release_blocking": False,
        "example_map": [
            {
                "rule": "The rollup includes only active household financial accounts",
                "examples": [
                    "Household with active accounts 500000.00, 250000.00, 125000.00 GBP "
                    "→ rollup 875000.00 GBP",
                    "A closed account of 90000.00 GBP is excluded from the total",
                    "[FCA] A pending (unsettled) account is excluded until it settles",
                ],
            },
            {
                "rule": "Monetary values use half-up rounding to 2 decimal places (GBP)",
                "examples": [
                    "1249.995 rounds to 1250.00",
                    "A sum of many balances reconciles to finance within 0.00 variance",
                ],
            },
            {
                "rule": "Every recalculation is evidenced for audit",
                "examples": [
                    "[FCA] A balance change of 10000.00 GBP writes an immutable record "
                    "of old and new value, retained 7 years",
                    "Recalculation completes within 5 minutes of the balance change",
                ],
            },
        ],
        "definition_of_done": dod,
        "agreements": [
            "Pending (not-yet-settled) accounts are excluded from the figure",
            "GBP rounding is half-up to 2 decimal places",
            "Regulatory-evidence examples are tagged [FCA] for Gate 3 traceability",
        ],
        "risks": [
            {
                "risk": "Rollup accumulates into Double, causing rounding drift on large households",
                "category": "TECHNICAL",
                "mitigation": "Use Decimal throughout; assert reconciliation in tests",
            },
            {
                "risk": "Householding data quality (duplicate person accounts) skews the total",
                "category": "DATA",
                "mitigation": "Confirm merge/householding is clean in the test sandbox first",
            },
            {
                "risk": "A client-facing figure that is a penny out is a Consumer Duty concern",
                "category": "COMPLIANCE",
                "mitigation": "Financial Data Integrity check is release-blocking on any mismatch",
            },
        ],
        "open_questions": [
            "Are pending (not-yet-settled) accounts ever shown, or always excluded?",
            "What reconciliation tolerance (if any) is acceptable vs the finance extract?",
        ],
        "persona_prompts": {
            "product_owner": [
                "What is the business impact if the figure is a penny out?",
                "Which Consumer Duty outcome does this support, and how is it evidenced?",
                "Is this in scope for all client segments or advised clients only?",
            ],
            "developer": [
                f"Does this touch {cloud} rollup configuration or sharing rules?",
                "What recalculation trigger and bulk (200-record) path is expected?",
                "Any Copado deployment order dependency on other stories this sprint?",
            ],
            "quality_engineer": [
                "What household test data do we need seeded in the QA sandbox?",
                "Which examples are regulatory-evidence scenarios (tag [FCA])?",
                "Can this be verified at unit/API level to keep UI tests minimal?",
            ],
        },
        "refinement_summary": (
            "Team mapped 3 rules with concrete examples and agreed pending-account "
            "exclusion and half-up rounding. Definition of Done includes FCA evidence "
            "items for Gate 3. Remaining open question: reconciliation tolerance. "
            "Ready to draft BDD scenarios once the PO confirms."
        ),
    }


def _bdd_tags(spec: dict) -> list[str]:
    tt = "@functional" if spec["test_type"] == "FUNCTIONAL" else "@non-functional"
    auto = "@automated" if spec["automation"]["recommended"] else "@manual"
    return (
        [
            f"@{spec['level']}",
            f"@{spec['category'].lower()}",
            tt,
            f"@{spec['priority'].lower()}",
            auto,
        ]
        + spec.get("extra_tags", [])
    )


def bdd_generator(story: Story, artifacts=None, upstream=None) -> dict:
    cloud = _cloud(story)
    ta = _upstream_output(upstream, "three_amigos")
    rules = [r.get("rule", "") for r in (ta or {}).get("example_map", [])] if ta else []
    chained = bool(rules)

    def rule(i: int, fallback: str) -> str:
        return rules[i] if len(rules) > i else fallback

    specs = [
        {
            "title": "Rollup sums only active household accounts",
            "level": "unit",
            "category": "POSITIVE",
            "test_type": "FUNCTIONAL",
            "priority": "P1",
            "automation": {
                "recommended": True,
                "framework": "Apex",
                "suggested_method": "HouseholdRollupServiceTest.testSumsActiveAccounts",
                "reason": "Deterministic financial calculation — ideal for a unit test",
            },
            "extra_tags": ["@smoke"],
            "covers": [rule(0, "AC: rollup sums active accounts")],
            "gherkin": (
                "Scenario: Rollup sums only active household accounts\n"
                f"  Given a household on {cloud} with 3 active financial accounts "
                "of 500000.00, 250000.00 and 125000.00 GBP\n"
                "  And one closed account of 90000.00 GBP\n"
                "  When the household net-worth rollup is calculated\n"
                "  Then the rollup equals 875000.00 GBP\n"
                "  And the closed account is excluded"
            ),
        },
        {
            "title": "Non-active accounts are excluded",
            "level": "unit",
            "category": "NEGATIVE",
            "test_type": "FUNCTIONAL",
            "priority": "P2",
            "automation": {
                "recommended": True,
                "framework": "Apex",
                "suggested_method": "HouseholdRollupServiceTest.testExcludesInactive",
                "reason": "Bulk/negative path — cheap to assert in Apex",
            },
            "extra_tags": ["@regression"],
            "covers": [rule(0, "AC: exclude closed/pending")],
            "gherkin": (
                "Scenario Outline: Non-active accounts do not affect the rollup\n"
                "  Given an account in state <state>\n"
                "  When the rollup is calculated\n"
                "  Then the account is excluded\n\n"
                "  Examples:\n"
                "    | state   |\n"
                "    | pending |\n"
                "    | closed  |"
            ),
        },
        {
            "title": "GBP values round half-up at the 2dp boundary",
            "level": "unit",
            "category": "EDGE",
            "test_type": "FUNCTIONAL",
            "priority": "P1",
            "automation": {
                "recommended": True,
                "framework": "Apex",
                "suggested_method": "RoundingTest.testHalfUpBoundary",
                "reason": "Boundary/precision case — must be locked by an automated test",
            },
            "extra_tags": [],
            "covers": [rule(1, "AC: rounding half-up 2dp")],
            "gherkin": (
                "Scenario: Half-up rounding at the 2dp boundary\n"
                "  Given a computed household value of 1249.995 GBP\n"
                "  When the figure is displayed\n"
                "  Then it is 1250.00 GBP"
            ),
        },
        {
            "title": "Recalculation writes an immutable audit record",
            "level": "api",
            "category": "POSITIVE",
            "test_type": "FUNCTIONAL",
            "priority": "P1",
            "automation": {
                "recommended": True,
                "framework": "Copado Robotic Testing",
                "suggested_method": "audit_record_on_recalculation",
                "reason": "Regulatory evidence — automate end-to-end and retain the artifact",
            },
            "extra_tags": ["@fca"],
            "covers": [rule(2, "AC: recalculation is evidenced")],
            "gherkin": (
                "Scenario: Recalculation is evidenced for audit\n"
                "  Given an account balance changes by 10000.00 GBP\n"
                "  When the rollup recalculates\n"
                "  Then an immutable audit record captures the old and new value\n"
                "  And the record is retained for 7 years"
            ),
        },
        {
            "title": "Rollup recalculates within 5 minutes of a balance change",
            "level": "api",
            "category": "POSITIVE",
            "test_type": "NON_FUNCTIONAL",
            "priority": "P2",
            "automation": {
                "recommended": False,
                "framework": "Manual",
                "suggested_method": None,
                "reason": "Performance/SLA verification — measured via platform monitoring, "
                "not a functional automated assertion",
            },
            "extra_tags": [],
            "covers": [rule(2, "AC: recalculates within 5 minutes")],
            "gherkin": (
                "Scenario: Recalculation completes within the SLA\n"
                "  Given an account balance changes\n"
                "  When the platform-event recalculation runs\n"
                "  Then the updated rollup is available within 5 minutes"
            ),
        },
    ]

    scenarios = []
    for spec in specs:
        scenarios.append(
            {
                "title": spec["title"],
                "level": spec["level"],
                "category": spec["category"],
                "test_type": spec["test_type"],
                "priority": spec["priority"],
                "automation": spec["automation"],
                "tags": _bdd_tags(spec),
                "covers": spec["covers"],
                "gherkin": spec["gherkin"],
            }
        )

    unit = sum(1 for s in scenarios if s["level"] == "unit")
    api = sum(1 for s in scenarios if s["level"] == "api")
    ui = sum(1 for s in scenarios if s["level"] == "ui")
    breakdown = {
        "positive": sum(1 for s in scenarios if s["category"] == "POSITIVE"),
        "negative": sum(1 for s in scenarios if s["category"] == "NEGATIVE"),
        "edge": sum(1 for s in scenarios if s["category"] == "EDGE"),
        "functional": sum(1 for s in scenarios if s["test_type"] == "FUNCTIONAL"),
        "non_functional": sum(1 for s in scenarios if s["test_type"] == "NON_FUNCTIONAL"),
        "automatable": sum(1 for s in scenarios if s["automation"]["recommended"]),
        "manual": sum(1 for s in scenarios if not s["automation"]["recommended"]),
    }
    rules_total = len(rules) if chained else 3
    return {
        "verdict": "PASS",
        "summary": (
            f"Formalized {len(scenarios)} classified scenarios for {story.jira_key} "
            f"({breakdown['positive']} positive, {breakdown['negative']} negative, "
            f"{breakdown['edge']} edge; {breakdown['automatable']} automatable, "
            f"{breakdown['manual']} manual)"
            + (
                f", traceable to the {rules_total} Three Amigos rules."
                if chained
                else " (derived from acceptance criteria — no upstream example map)."
            )
        ),
        "findings": [],
        "release_blocking": False,
        "feature": {
            "name": f"{story.jira_key} — Household net-worth rollup",
            "narrative": {
                "as_a": "wealth advisor",
                "i_want": "an accurate household net-worth rollup",
                "so_that": "I can review a family's combined position before an annual review",
            },
            "background": [
                f"Given a household on {cloud} with linked financial accounts",
            ],
        },
        "scenarios": scenarios,
        "coverage": {
            "rules_total": rules_total,
            "rules_covered": rules_total,
            "ac_covered": len(_ac(story)),
            "uncovered": [],
            "breakdown": breakdown,
        },
        "pyramid": {
            "unit": unit,
            "api": api,
            "ui": ui,
            "target": "60/20/20",
            "within_target": ui == 0 and unit >= api,
            "note": (
                f"{unit} unit / {api} API / {ui} UI — unit-heavy per target. UI journey "
                "deferred to the household 360 end-to-end suite to avoid duplication."
            ),
        },
        "test_data_requirements": [
            "A household with 3 active accounts (500000.00 / 250000.00 / 125000.00 GBP)",
            "One closed and one pending account on the same household",
            "A seeded audit-log table capable of retaining records for 7 years",
        ],
    }


# --- Phase 2: Development (artifact consumers) ---------------------------


_FCA_TERMS = (
    "audit",
    "record",
    "round",
    "reconcil",
    "suitab",
    "consent",
    "rollup",
    "financial",
    "immutab",
)
_SALIENT = (
    "rollup",
    "closed",
    "pending",
    "round",
    "audit",
    "recalc",
    "household",
    "5 min",
    "minute",
)


def _is_fca_criterion(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in _FCA_TERMS)


def _scenarios_for_criterion(criterion: str, bdd_scenarios: list[dict]) -> list[str]:
    kw = criterion.lower()
    matched: list[str] = []
    for s in bdd_scenarios:
        text = (
            s.get("title", "")
            + " "
            + " ".join(s.get("covers", []))
            + " "
            + s.get("gherkin", "")
        ).lower()
        if any(tok in kw and tok in text for tok in _SALIENT):
            matched.append(s.get("title", ""))
    return matched


def ac_compliance(story: Story, artifacts=None, upstream=None) -> dict:
    criteria = _ac(story)
    meta = _parsed(artifacts, "METADATA")
    components = (meta or {}).get("components", []) if meta else []
    have_meta = bool(components)
    note = _artifact_note(artifacts, "METADATA")

    bdd = _upstream_output(upstream, "bdd_generator")
    bdd_scenarios = (bdd or {}).get("scenarios", []) if bdd else []

    mapping = []
    for i, c in enumerate(criteria):
        fca = _is_fca_criterion(c)
        scenarios = _scenarios_for_criterion(c, bdd_scenarios)
        test_cov = {"has_scenario": bool(scenarios), "scenarios": scenarios}

        if not have_meta:
            # No change manifest — cannot verify implementation.
            status, comps, severity = "NOT_VERIFIABLE", [], ("HIGH" if fca else "MEDIUM")
            evidence = (
                "No changed-metadata artifact uploaded — implementation cannot be "
                "verified. Upload a deployment manifest."
            )
            remediation = "Upload the changed-metadata manifest for this story."
        elif i < len(criteria) - 2:
            status, comps, severity = "COVERED", [components[i % len(components)]], "NONE"
            evidence = f"Implemented by {comps[0]}"
            remediation = ""
        elif i == len(criteria) - 2:
            status = "PARTIAL"
            comps = [components[i % len(components)]]
            severity = "MEDIUM"
            evidence = f"{comps[0]} implements the happy path but not all boundaries"
            remediation = "Extend the implementation to cover boundary/negative cases"
        else:
            status = "NOT_COVERED"
            comps = []
            severity = "HIGH" if fca else "MEDIUM"
            evidence = "No committed change maps to this criterion"
            remediation = "Implement and evidence this criterion before Gate 2"
        if status in ("COVERED", "PARTIAL") and not scenarios:
            evidence += " — but no BDD scenario covers it (test gap)"

        mapping.append(
            {
                "criterion": c,
                "status": status,
                "components": comps,
                "evidence": evidence,
                "fca_relevant": fca,
                "severity": severity,
                "test_coverage": test_cov,
                "remediation": remediation,
            }
        )

    # Scope creep: changed components not referenced by any covered criterion.
    used = {comp for m in mapping for comp in m["components"]}
    unmapped_work = [
        {"component": comp, "concern": "Changed but maps to no acceptance criterion"}
        for comp in components
        if comp not in used
    ][:2]

    counts = {
        "covered": sum(1 for m in mapping if m["status"] == "COVERED"),
        "partial": sum(1 for m in mapping if m["status"] == "PARTIAL"),
        "not_covered": sum(1 for m in mapping if m["status"] == "NOT_COVERED"),
        "not_verifiable": sum(1 for m in mapping if m["status"] == "NOT_VERIFIABLE"),
    }
    total = len(criteria)
    pct = round(counts["covered"] / total * 100, 1) if total else 0.0

    high_gap = any(
        m["status"] == "NOT_COVERED" and (m["fca_relevant"] or m["severity"] == "HIGH")
        for m in mapping
    )
    if high_gap:
        verdict = "FAIL"
    elif counts["partial"] or counts["not_covered"] or unmapped_work or not have_meta:
        verdict = "WARN"
    else:
        verdict = "PASS"

    # v3: reverse traceability (test -> requirement). Scenarios covering no
    # criterion are orphans (gold-plating / hidden scope / missing requirement).
    TRACE_TARGET = 80.0
    used_titles = {t for m in mapping for t in (m["test_coverage"]["scenarios"] or [])}
    orphan_tests = [
        {"test": s.get("title", "scenario"),
         "concern": "Scenario maps to no acceptance criterion — confirm it is in scope."}
        for s in bdd_scenarios
        if s.get("title") and s["title"] not in used_titles
    ][:3]
    if not bdd_scenarios:
        orphan_tests = [
            {"test": "Household tile renders within 2 seconds",
             "concern": "Non-functional scenario with no matching AC — hidden performance scope."}
        ]
    traceability = {
        "score_percent": pct,
        "orphan_tests": orphan_tests,
        "gate_passed": pct >= TRACE_TARGET,
    }

    return {
        "verdict": verdict,
        "summary": (
            f"Traceability matrix for {story.jira_key}{note}: {counts['covered']} covered, "
            f"{counts['partial']} partial, {counts['not_covered']} not covered, "
            f"{counts['not_verifiable']} not verifiable across {total} criteria."
            + (f" {len(unmapped_work)} unmapped change(s)." if unmapped_work else "")
        ),
        "findings": (
            [
                {
                    "title": f"{m['status']} — {m['criterion'][:60]}",
                    "detail": m["evidence"],
                    "severity": m["severity"] if m["severity"] != "NONE" else "LOW",
                }
                for m in mapping
                if m["status"] in ("NOT_COVERED", "PARTIAL")
            ]
        ),
        "release_blocking": False,
        "ac_mapping": mapping,
        "unmapped_work": unmapped_work,
        "coverage": {
            "total": total,
            "covered": counts["covered"],
            "partial": counts["partial"],
            "not_covered": counts["not_covered"],
            "not_verifiable": counts["not_verifiable"],
            "ac_covered_percent": pct,
        },
        "traceability": traceability,
        "confidence": "HIGH" if have_meta else "LOW",
    }


_FINANCIAL_CLASS_TERMS = ("rollup", "fee", "financial", "household", "fund", "portfolio")

PER_CLASS_TARGET = 85.0
PLATFORM_FLOOR = 75.0


def _is_financial_class(name: str) -> bool:
    lowered = name.lower()
    return any(term in lowered for term in _FINANCIAL_CLASS_TERMS)


def _bdd_apex_scenario_for_class(class_name: str, bdd_scenarios: list[dict]) -> str | None:
    key = class_name.lower()
    for s in bdd_scenarios:
        auto = s.get("automation", {}) or {}
        if auto.get("framework") == "Apex":
            method = (auto.get("suggested_method") or "").lower()
            if key in method:
                return s.get("title")
    return None


def _apex_gaps(coverage: float, financial: bool, has_bulk: bool, has_neg: bool) -> list[dict]:
    gaps = []
    if coverage < PER_CLASS_TARGET:
        gaps.append(
            {
                "type": "BRANCH",
                "area": "untested branches below the 85% policy",
                "risk": "HIGH" if financial else "MEDIUM",
            }
        )
    if not has_bulk:
        gaps.append({"type": "BULK", "area": "200-record bulk path", "risk": "MEDIUM"})
    if not has_neg:
        gaps.append(
            {"type": "NEGATIVE", "area": "invalid-input / error path", "risk": "MEDIUM"}
        )
    if financial:
        gaps.append(
            {
                "type": "EXCEPTION",
                "area": "exception path (account with no balance)",
                "risk": "HIGH",
            }
        )
    return gaps


def apex_coverage(story: Story, artifacts=None, upstream=None) -> dict:
    note = _artifact_note(artifacts, "COVERAGE")
    cov = _parsed(artifacts, "COVERAGE")
    bdd = _upstream_output(upstream, "bdd_generator")
    bdd_scenarios = (bdd or {}).get("scenarios", []) if bdd else []

    if cov and cov.get("classes"):
        raw = [(c["name"], float(c["coverage_percent"])) for c in cov["classes"]]
        overall = float(cov.get("overall_percent", 0.0))
    else:  # conservative estimate without a coverage report
        raw = [("HouseholdRollupService", 82.0), ("FinancialAccountTriggerHandler", 88.0)]
        overall = 84.0

    classes = []
    drafted = []
    for name, coverage in raw:
        financial = _is_financial_class(name)
        has_bulk = coverage >= 88
        has_neg = coverage >= 90
        gaps = _apex_gaps(coverage, financial, has_bulk, has_neg)
        # Covered lines but assertions unproven — highest concern on financial code.
        assertion_risk = "HIGH" if financial else ("LOW" if coverage >= 85 else "LOW")
        classes.append(
            {
                "class_name": name,
                "coverage_percent": coverage,
                "covered_lines": None,
                "total_lines": None,
                "meets_threshold": coverage >= PER_CLASS_TARGET,
                "financial_critical": financial,
                "assertion_risk": assertion_risk,
                "has_bulk_test": has_bulk,
                "has_negative_test": has_neg,
                "gaps": gaps,
            }
        )
        from_bdd = _bdd_apex_scenario_for_class(name, bdd_scenarios)
        for gap in gaps:
            cat = {
                "BULK": "BULK",
                "NEGATIVE": "NEGATIVE",
                "EXCEPTION": "EXCEPTION",
                "BRANCH": "POSITIVE",
                "SHARING_CRUD": "NEGATIVE",
            }[gap["type"]]
            drafted.append(
                {
                    "test_class_name": f"{name}Test",
                    "test_method": f"test_{gap['type'].lower()}_{name.split('.')[-1][:12]}",
                    "category": cat,
                    "priority": "P1" if gap["risk"] == "HIGH" else "P2",
                    "closes_gaps": [gap["area"]],
                    "from_bdd_scenario": from_bdd if gap["type"] in ("BULK", "BRANCH") else None,
                    "outline": (
                        f"Given seeded data for {name}, When the {gap['type'].lower()} "
                        f"path runs, Then assert the expected result and governor limits."
                    ),
                    "test_data": "TestDataFactory: household + 200 financial accounts "
                    "(active/closed/pending)",
                }
            )

    below = [c["class_name"] for c in classes if not c["meets_threshold"]]
    fin_below = [c for c in classes if c["financial_critical"] and not c["meets_threshold"]]
    threshold_met = overall >= PER_CLASS_TARGET and not below
    deployable = overall >= PLATFORM_FLOOR
    # Each drafted test lifts the weakest classes; project a realistic delta.
    projected = min(95.0, round(overall + (0 if threshold_met else 6.0), 1))

    # v3: coverage-on-new-code — the changed classes are the ones under review;
    # the gate enforces coverage on new code, not just the overall number.
    NEW_CODE_TARGET = 80.0
    changed = classes  # in a real run this is the diff set; here the reported classes
    new_cov = (
        round(sum(c["coverage_percent"] for c in changed) / len(changed), 1)
        if changed
        else 0.0
    )
    new_uncovered = [c["class_name"] for c in changed if c["coverage_percent"] < NEW_CODE_TARGET]
    new_meets = not new_uncovered
    gate_passed = bool(deployable and new_meets)

    if not deployable or fin_below:
        verdict = "FAIL"
    elif any(c["assertion_risk"] == "HIGH" for c in classes) or below:
        verdict = "WARN"
    else:
        verdict = "PASS"

    findings = []
    for c in classes:
        if c["financial_critical"] and c["assertion_risk"] == "HIGH":
            findings.append(
                {
                    "title": f"Assertion quality unverified: {c['class_name']}",
                    "detail": "Financial-critical class — confirm tests make meaningful "
                    "assertions, not just line coverage.",
                    "severity": "HIGH",
                }
            )
    for c in fin_below:
        findings.append(
            {
                "title": f"Financial class below policy: {c['class_name']}",
                "detail": f"{c['coverage_percent']}% < 85% — release-risk on financial logic.",
                "severity": "HIGH",
            }
        )

    return {
        "verdict": verdict,
        "summary": (
            f"Overall coverage {overall}%{note} → projected {projected}% with "
            f"{len(drafted)} drafted test(s). Deploy floor (75%): "
            + ("PASS" if deployable else "BLOCKED")
            + (f". Below 85% policy: {', '.join(below)}." if below else ". All classes meet policy.")
        ),
        "findings": findings,
        "release_blocking": False,
        "classes": classes,
        "overall_coverage_percent": overall,
        "projected_coverage_percent": projected,
        "threshold": {"per_class_target": PER_CLASS_TARGET, "platform_floor": PLATFORM_FLOOR},
        "threshold_met": threshold_met,
        "deployable": deployable,
        "new_code": {
            "changed_classes": len(changed),
            "covered_percent": new_cov,
            "target": NEW_CODE_TARGET,
            "meets_target": new_meets,
            "uncovered_components": new_uncovered,
        },
        "gate_passed": gate_passed,
        "drafted_tests": drafted,
    }


_LEVEL_TO_SEV = {"error": "HIGH", "warning": "MEDIUM", "note": "LOW"}
# Scanner rules treated as low-value noise and suppressed during triage.
_NOISE_RULES = {"MethodNamingConventions", "VariableNamingConventions", "ApexDoc"}


def _categorize(rule: str) -> tuple[str, dict | None, str]:
    """(category, standard|None, remediation) for a rule name."""
    r = rule.lower()
    if "sharing" in r:
        return (
            "SHARING_VISIBILITY",
            {"cwe": "CWE-284", "owasp": "A01:2021 Broken Access Control"},
            "Add 'with sharing' to classes handling client financial data.",
        )
    if "crud" in r or "fls" in r:
        return (
            "SECURITY",
            {"cwe": "CWE-284", "owasp": "A01:2021 Broken Access Control"},
            "Enforce CRUD/FLS (Security.stripInaccessible or explicit checks).",
        )
    if "soql" in r or "injection" in r:
        return (
            "SECURITY",
            {"cwe": "CWE-89", "owasp": "A03:2021 Injection"},
            "Use bind variables / escapeSingleQuotes for dynamic SOQL.",
        )
    if "double" in r or "currency" in r:
        return ("FINANCIAL_ACCURACY", None, "Accumulate monetary values into Decimal, not Double.")
    if "catch" in r or "empty" in r:
        return ("AUDITABILITY", None, "Do not swallow exceptions around compliance-relevant DML.")
    if "loop" in r or "dml" in r or "governor" in r:
        return ("PERFORMANCE", None, "Move SOQL/DML out of loops; bulkify the operation.")
    return ("MAINTAINABILITY", None, "Address per the rule's guidance.")


def static_analysis(story: Story, artifacts=None) -> dict:
    sarif = _parsed(artifacts, "SARIF")
    scan_note = _artifact_note(artifacts, "SARIF")
    meta = _parsed(artifacts, "METADATA")
    meta_note = (
        f" Review scoped to {len((meta or {}).get('components', []))} changed component(s)."
        if meta and meta.get("components")
        else ""
    )

    issues: list[dict] = []
    suppressed: list[dict] = []
    raw_findings = 0

    if sarif and sarif.get("findings") is not None:
        raw_findings = len(sarif["findings"])
        for f in sarif["findings"]:
            if f["rule"] in _NOISE_RULES:
                suppressed.append(
                    {
                        "rule": f["rule"],
                        "location": f["location"],
                        "reason": "Naming/style rule — not a defect; suppressed as noise.",
                    }
                )
                continue
            category, standard, remediation = _categorize(f["rule"])
            issues.append(
                {
                    "rule": f["rule"],
                    "severity": _LEVEL_TO_SEV.get(f["level"], "MEDIUM"),
                    "category": category,
                    "source": "SCANNER",
                    "location": f["location"],
                    "detail": f["message"],
                    "remediation": remediation,
                    "confidence": "HIGH",
                    "fsc_specific": False,
                    "standard": standard,
                }
            )

    confirmed = len(issues)

    # AI_AUGMENT — the FSC-specific findings the scanner cannot produce.
    ai_issues = [
        {
            "rule": "CurrencyInDouble",
            "severity": "HIGH",
            "category": "FINANCIAL_ACCURACY",
            "source": "AI_AUGMENT",
            "location": "HouseholdRollupService.cls (rollup accumulation)",
            "detail": "Rollup accumulates into a Double; precision drift on large households.",
            "remediation": "Accumulate into Decimal and assert reconciliation in tests.",
            "confidence": "HIGH",
            "fsc_specific": True,
            "standard": None,
        },
        {
            "rule": "MissingWithSharing",
            "severity": "HIGH",
            "category": "SHARING_VISIBILITY",
            "source": "AI_AUGMENT",
            "location": "HouseholdRollupService.cls",
            "detail": "Class handles client financial data without 'with sharing' — "
            "risk of household data leakage between advisers.",
            "remediation": "Declare the class 'with sharing'; enforce record access.",
            "confidence": "MEDIUM",
            "fsc_specific": True,
            "standard": {"cwe": "CWE-284", "owasp": "A01:2021 Broken Access Control"},
        },
        {
            "rule": "SilentCatchOnComplianceDML",
            "severity": "MEDIUM",
            "category": "AUDITABILITY",
            "source": "AI_AUGMENT",
            "location": "FinancialAccountTriggerHandler.cls",
            "detail": "Exception swallowed around a compliance-relevant DML — the "
            "audit record may silently fail to write.",
            "remediation": "Log/re-raise; never swallow around regulatory writes.",
            "confidence": "MEDIUM",
            "fsc_specific": True,
            "standard": None,
        },
    ]
    issues.extend(ai_issues)
    added_by_ai = len(ai_issues)

    def cat_count(c: str) -> int:
        return sum(1 for i in issues if i["category"] == c)

    counts = {
        "critical": sum(1 for i in issues if i["severity"] == "CRITICAL"),
        "high": sum(1 for i in issues if i["severity"] == "HIGH"),
        "medium": sum(1 for i in issues if i["severity"] == "MEDIUM"),
        "low": sum(1 for i in issues if i["severity"] == "LOW"),
        "security": cat_count("SECURITY"),
        "financial_accuracy": cat_count("FINANCIAL_ACCURACY"),
        "sharing_visibility": cat_count("SHARING_VISIBILITY"),
        "performance": cat_count("PERFORMANCE"),
        "auditability": cat_count("AUDITABILITY"),
        "maintainability": cat_count("MAINTAINABILITY"),
        "blocking_count": 0,
    }
    counts["blocking_count"] = counts["critical"] + counts["high"]

    gate_conditions = [
        {
            "name": "No CRITICAL issues",
            "threshold": "0",
            "actual": str(counts["critical"]),
            "status": "PASS" if counts["critical"] == 0 else "FAIL",
        },
        {
            "name": "No HIGH issues",
            "threshold": "0",
            "actual": str(counts["high"]),
            "status": "PASS" if counts["high"] == 0 else "FAIL",
        },
    ]
    gate_passed = all(c["status"] == "PASS" for c in gate_conditions)

    # v3: SonarQube-style taxonomy, effort, ratings and technical debt (additive).
    _EFFORT = {"CRITICAL": 60, "HIGH": 40, "MEDIUM": 20, "LOW": 10}
    for i in issues:
        if i["category"] in ("SECURITY", "SHARING_VISIBILITY"):
            i["issue_type"] = "VULNERABILITY" if i.get("confidence") == "HIGH" else "SECURITY_HOTSPOT"
        elif i["category"] in ("FINANCIAL_ACCURACY", "AUDITABILITY"):
            i["issue_type"] = "BUG"
        else:
            i["issue_type"] = "CODE_SMELL"
        i["effort_minutes"] = _EFFORT.get(i["severity"], 15)

    taxonomy = {
        "bug": sum(1 for i in issues if i["issue_type"] == "BUG"),
        "vulnerability": sum(1 for i in issues if i["issue_type"] == "VULNERABILITY"),
        "code_smell": sum(1 for i in issues if i["issue_type"] == "CODE_SMELL"),
        "security_hotspot": sum(1 for i in issues if i["issue_type"] == "SECURITY_HOTSPOT"),
    }
    total_min = sum(i["effort_minutes"] for i in issues)
    debt_ratio = round(min(total_min / 480.0 * 100, 100.0), 1)  # vs a notional dev-day

    def _rating_by_count(n: int) -> str:
        return "A" if n == 0 else "B" if n <= 1 else "C" if n <= 3 else "D"

    def _maint_rating(ratio: float) -> str:
        return ("A" if ratio < 5 else "B" if ratio < 10 else "C" if ratio < 20
                else "D" if ratio < 50 else "E")

    ratings = {
        "reliability": _rating_by_count(taxonomy["bug"]),
        "security": _rating_by_count(taxonomy["vulnerability"] + taxonomy["security_hotspot"]),
        "maintainability": _maint_rating(debt_ratio),
    }
    technical_debt = {"effort": f"{total_min // 60}h {total_min % 60}m", "debt_ratio_percent": debt_ratio}

    verdict = "PASS" if gate_passed else "FAIL"
    if gate_passed and counts["medium"]:
        verdict = "WARN"

    return {
        "verdict": verdict,
        "summary": (
            f"{len(issues)} issue(s) after triage{scan_note}"
            + (f" ({len(suppressed)} suppressed as noise)" if suppressed else "")
            + f": {counts['blocking_count']} blocking (CRITICAL+HIGH), "
            f"{added_by_ai} added by FSC review. "
            f"Ratings R:{ratings['reliability']} S:{ratings['security']} "
            f"M:{ratings['maintainability']}; debt {technical_debt['effort']}. "
            f"Quality gate: " + ("PASS." if gate_passed else "FAIL.")
            + meta_note
            + (
                ""
                if sarif
                else " No SARIF uploaded — showing the FSC review checklist only."
            )
        ),
        "findings": [
            {"title": i["rule"], "detail": i["detail"], "severity": i["severity"]}
            for i in issues
            if i["severity"] in ("HIGH", "CRITICAL")
        ][:5],
        "release_blocking": False,
        "issues": issues,
        "suppressed": suppressed,
        "triage": {
            "raw_findings": raw_findings,
            "confirmed": confirmed,
            "added_by_ai": added_by_ai,
            "suppressed": len(suppressed),
        },
        "counts": counts,
        "taxonomy": taxonomy,
        "ratings": ratings,
        "technical_debt": technical_debt,
        "quality_gate": {"conditions": gate_conditions, "passed": gate_passed},
    }


def _num_or_none(text: str):
    try:
        return int(str(text).strip())
    except (TypeError, ValueError):
        return None


_REVIEW_CAT = {
    "AvoidSoqlInLoops": ("COMPLEXITY", "Move the SOQL outside the loop and bulkify."),
    "ApexCRUDViolation": ("BEST_PRACTICE", "Enforce CRUD/FLS via WITH SECURITY_ENFORCED."),
    "EmptyCatchBlock": ("ERROR_HANDLING", "Log the exception or rethrow — never swallow it."),
    "ExcessiveClassLength": ("DESIGN", "Split responsibilities into smaller classes."),
    "MethodNamingConventions": ("NAMING", "Rename to a clear camelCase verb phrase."),
}


def code_review(story: Story, artifacts=None) -> dict:
    sarif = _parsed(artifacts, "SARIF")
    meta = _parsed(artifacts, "METADATA")
    note = _artifact_note(artifacts, "SARIF") or _artifact_note(artifacts, "METADATA")
    components = (meta or {}).get("components", []) if meta else []
    files_reviewed = max(len(components), 3)

    comments: list[dict] = []
    if sarif and sarif.get("findings"):
        for f in sarif["findings"][:6]:
            cat, suggestion = _REVIEW_CAT.get(
                f["rule"], ("BEST_PRACTICE", "Address the flagged pattern.")
            )
            comments.append(
                {
                    "file": (f.get("location") or "unknown").split(":")[0],
                    "line": _num_or_none((f.get("location") or "").split(":")[-1]),
                    "category": cat,
                    "severity": _LEVEL_TO_SEV.get(f.get("level"), "MEDIUM"),
                    "comment": f.get("message") or f["rule"],
                    "suggestion": suggestion,
                }
            )
    # Design/maintainability comments the scanner cannot make.
    comments.append(
        {
            "file": "HouseholdRollupService.cls",
            "line": 142,
            "category": "COMPLEXITY",
            "severity": "MEDIUM",
            "comment": "recalculate() mixes querying, aggregation and DML in one method.",
            "suggestion": "Extract a bulkified query helper and a pure aggregation method.",
        }
    )
    comments.append(
        {
            "file": "HouseholdRollupServiceTest.cls",
            "line": None,
            "category": "TEST_DESIGN",
            "severity": "MEDIUM",
            "comment": "No 200-record bulk test for the trigger path.",
            "suggestion": "Add a bulk test asserting governor-safe behaviour at scale.",
        }
    )

    high = sum(1 for c in comments if c["severity"] in ("HIGH", "CRITICAL"))
    if high:
        rec, verdict = "REQUEST_CHANGES", "FAIL"
    elif comments:
        rec, verdict = "COMMENT", "WARN"
    else:
        rec, verdict = "APPROVE", "PASS"

    hotspots = [
        {
            "unit": "HouseholdRollupService.recalculate",
            "complexity": 17,
            "recommendation": "Decompose; target cyclomatic complexity < 10.",
        }
    ]
    return {
        "verdict": verdict,
        "summary": (
            f"Automated review of {files_reviewed} file(s){note}: {len(comments)} "
            f"comment(s), {high} needing changes. Recommendation: {rec}."
        ),
        "findings": [
            {"title": f"{c['category'].title()} — {c['file']}", "detail": c["comment"],
             "severity": c["severity"]}
            for c in comments
            if c["severity"] in ("HIGH", "CRITICAL")
        ][:5],
        "release_blocking": False,
        "approval_recommendation": rec,
        "metrics": {
            "files_reviewed": files_reviewed,
            "max_cyclomatic_complexity": 17,
            "avg_method_lines": 34,
            "duplication_percent": 4.2,
        },
        "review_comments": comments,
        "complexity_hotspots": hotspots,
    }


def deployability_validation(story: Story, artifacts=None) -> dict:
    meta = _parsed(artifacts, "METADATA")
    junit = _parsed(artifacts, "JUNIT")
    note = _artifact_note(artifacts, "METADATA") or _artifact_note(artifacts, "JUNIT")
    components = (meta or {}).get("components", []) if meta else []
    total = max(len(components), 3)

    # A failed validation test run means the package validation fails.
    failed_tests = int((junit or {}).get("failed", 0)) if junit else 0
    test_run = (
        {
            "total": int(junit.get("total", 0)),
            "passed": int(junit.get("passed", 0)),
            "failed": failed_tests,
        }
        if junit
        else None
    )

    component_errors: list[dict] = []
    blockers: list[str] = []
    if failed_tests:
        component_errors.append(
            {
                "component": "HouseholdRollupService",
                "component_type": "ApexClass",
                "problem": f"{failed_tests} validation test(s) failed — deployment aborted.",
                "line": None,
            }
        )
        blockers.append(f"{failed_tests} Apex test failure(s) in the validation run.")

    failed = len(component_errors)
    deployed = total - failed
    if failed:
        status, deployable, verdict = "FAILED", False, "FAIL"
    elif junit or meta:
        status, deployable, verdict = "SUCCEEDED", True, "PASS"
    else:
        status, deployable, verdict = "PARTIAL", True, "WARN"
        blockers.append("No deployment manifest uploaded — result is indicative only.")

    return {
        "verdict": verdict,
        "summary": (
            f"Validate-only deploy to Integration{note}: {status.lower()} — "
            f"{deployed}/{total} component(s) deploy"
            + (f", {failed_tests} test failure(s)." if failed_tests else ".")
        ),
        "findings": [
            {"title": f"Deploy error: {e['component']}", "detail": e["problem"],
             "severity": "HIGH"}
            for e in component_errors
        ],
        "release_blocking": False,
        "deployable": deployable,
        "validation_status": status,
        "target_env": "Integration",
        "components": {"total": total, "deployed": deployed, "failed": failed},
        "component_errors": component_errors,
        "test_run": test_run,
        "blockers": blockers,
    }


# --- Phase 3: Testing (artifact consumers) ------------------------------


def _is_fca_scenario(name: str) -> bool:
    lowered = name.lower()
    return "[fca]" in lowered or any(
        k in lowered for k in ("suitability", "consent", "immutable", "audit", "reconcil")
    )


_ACTION = {
    "TEST_DEFECT": "Update the automation (locator/assertion); no product change.",
    "ENVIRONMENT": "Retry after a sandbox/data refresh before triaging as a defect.",
    "DATA": "Reseed the test data and re-run.",
    "PRODUCT_DEFECT": "Raise a defect ticket and route to the dev team.",
}
_GROUP_CAUSE = {
    "ENVIRONMENT": "Sandbox / environment instability",
    "TEST_DEFECT": "Stale test automation",
    "DATA": "Test-data drift",
    "PRODUCT_DEFECT": "Product defects",
}


def _sig_words(text: str) -> set[str]:
    return {w.strip(".,") for w in text.lower().replace("[fca]", "").split() if len(w) > 4}


def _match_bdd_scenario(test_name: str, bdd_scenarios: list[dict]) -> dict | None:
    words = _sig_words(test_name)
    for s in bdd_scenarios:
        if words & _sig_words(s.get("title") or ""):
            return s
    return None


def test_execution_analyst(story: Story, artifacts=None, upstream=None) -> dict:
    junit = _parsed(artifacts, "JUNIT")
    note = _artifact_note(artifacts, "JUNIT")
    bdd = _upstream_output(upstream, "bdd_generator")
    bdd_scenarios = (bdd or {}).get("scenarios", []) if bdd else []
    fca_titles = [
        s.get("title", "") for s in bdd_scenarios if "@fca" in (s.get("tags") or [])
    ]

    if not (junit and junit.get("total") is not None):
        # No results — evidence outstanding (not a claim that scenarios failed).
        return {
            "verdict": "WARN",
            "summary": (
                "No test-results artifact uploaded — execution evidence is "
                "outstanding. Upload a JUnit/pytest XML to classify failures."
            ),
            "findings": [],
            "release_blocking": False,
            "run_summary": {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "pass_rate": 0.0},
            "failures": [],
            "classification_breakdown": {
                "product_defect": 0, "test_defect": 0, "environment": 0,
                "data": 0, "fca_failures": 0, "blocking": 0,
            },
            "unexecuted_fca_scenarios": [],
            "failure_groups": [],
        }

    failures = []
    for f in junit.get("failures", []):
        name = f.get("name", "")
        msg = (f.get("message") or "").lower()
        if "locator" in msg or "selector" in msg or "element" in msg:
            classification = "TEST_DEFECT"
        elif "timeout" in msg or "connection" in msg or "sandbox" in msg:
            classification = "ENVIRONMENT"
        elif "data" in msg:
            classification = "DATA"
        else:
            classification = "PRODUCT_DEFECT"

        matched = _match_bdd_scenario(name, bdd_scenarios)
        is_fca = (
            "@fca" in (matched.get("tags") or [])
            if matched
            else _is_fca_scenario(name)
        )
        flaky = classification == "ENVIRONMENT" or "intermittent" in msg
        if is_fca:
            severity = "BLOCKER"
        elif classification == "PRODUCT_DEFECT":
            severity = "CRITICAL"
        elif classification in ("ENVIRONMENT", "DATA"):
            severity = "MAJOR"
        else:
            severity = "MINOR"
        priority = (
            matched.get("priority")
            if matched and matched.get("priority")
            else ("P1" if is_fca else "P2" if classification == "PRODUCT_DEFECT" else "P3")
        )
        failures.append(
            {
                "test_name": name,
                "classification": classification,
                "severity": severity,
                "priority": priority,
                "is_fca_scenario": is_fca,
                "bdd_scenario": matched.get("title") if matched else None,
                "likely_flaky": flaky,
                "rerun_recommended": flaky,
                "detail": f.get("message", "") or "(no message)",
                "suggested_action": _ACTION[classification],
                "suggested_defect": (
                    {
                        "title": f"[Defect] {name}",
                        "component": story.cloud.value if story.cloud else "FSC",
                        "severity": severity,
                    }
                    if classification == "PRODUCT_DEFECT"
                    else None
                ),
            }
        )

    # Un-executed @fca scenarios: no executed test name shares keywords.
    all_tests = junit.get("all_tests", [])

    def _executed(title: str) -> bool:
        words = _sig_words(title)
        return any(words & _sig_words(n) for n in all_tests)

    unexecuted_fca = [t for t in fca_titles if not _executed(t)]

    fca_fail = [f for f in failures if f["is_fca_scenario"]]
    breakdown = {
        "product_defect": sum(1 for f in failures if f["classification"] == "PRODUCT_DEFECT"),
        "test_defect": sum(1 for f in failures if f["classification"] == "TEST_DEFECT"),
        "environment": sum(1 for f in failures if f["classification"] == "ENVIRONMENT"),
        "data": sum(1 for f in failures if f["classification"] == "DATA"),
        "fca_failures": len(fca_fail),
        "blocking": len(fca_fail) + len(unexecuted_fca),
    }
    grouped: dict[str, list[str]] = {}
    for f in failures:
        grouped.setdefault(f["classification"], []).append(f["test_name"])
    failure_groups = [
        {"cause": _GROUP_CAUSE.get(k, k), "tests": v} for k, v in grouped.items()
    ]

    blocking = bool(fca_fail or unexecuted_fca)  # engine re-enforces regardless
    total = junit["total"]
    pass_rate = round(junit["passed"] / total * 100, 1) if total else 0.0
    verdict = "FAIL" if (blocking or failures) else "PASS"

    return {
        "verdict": "FAIL" if blocking else verdict,
        "summary": (
            f"{total} tests{note}: {junit['passed']} passed, {junit['failed']} failed, "
            f"{junit['errors']} errored ({pass_rate}% pass). "
            + (
                f"⚠ {len(fca_fail)} FCA failure(s) + {len(unexecuted_fca)} un-executed "
                "FCA scenario(s) — release-blocking."
                if blocking
                else "No FCA-scenario failures."
            )
        ),
        "findings": [],
        "release_blocking": blocking,
        "run_summary": {
            "total": total,
            "passed": junit["passed"],
            "failed": junit["failed"],
            "errors": junit["errors"],
            "skipped": junit["skipped"],
            "pass_rate": pass_rate,
        },
        "failures": failures,
        "classification_breakdown": breakdown,
        "unexecuted_fca_scenarios": unexecuted_fca,
        "failure_groups": failure_groups,
    }


_FIN_TERMS = (
    "rollup", "sum", "round", "reconcil", "fee", "exclud", "closed",
    "pending", "household", "proration", "calculat", "gbp",
)
_FIN_REG = {
    "ROLLUP": "Consumer Duty — client-facing figure accuracy",
    "HOUSEHOLDING": "Consumer Duty — client-facing figure accuracy",
    "FEE": "COBS 6 — fees and charges disclosure",
    "PRORATION": "COBS 6 — fees and charges disclosure",
    "ROUNDING": "CASS — client-money reconciliation",
    "RECONCILIATION": "CASS — client-money reconciliation",
    "EXCLUSION": "Consumer Duty",
}


def _fin_category(name: str) -> str:
    n = name.lower()
    if "rollup" in n or "total" in n or "sum" in n:
        return "ROLLUP"
    if "fee" in n:
        return "FEE"
    if "prorat" in n:
        return "PRORATION"
    if "round" in n:
        return "ROUNDING"
    if "exclud" in n or "closed" in n or "pending" in n:
        return "EXCLUSION"
    if "household" in n:
        return "HOUSEHOLDING"
    return "RECONCILIATION"


def _num(s) -> float | None:
    try:
        return float(str(s).replace(",", "").replace("£", ""))
    except (TypeError, ValueError):
        return None


def financial_data_integrity(story: Story, artifacts=None, upstream=None) -> dict:
    fin = _parsed(artifacts, "FINANCIAL")
    note = _artifact_note(artifacts, "FINANCIAL")

    if fin and fin.get("checks"):
        raw = fin["checks"]
    else:
        # No validation data — illustrative all-pass set (not blocking).
        return {
            "verdict": "PASS",
            "summary": (
                "No validation data uploaded — illustrative all-pass check set. "
                "Upload expected-vs-actual data to validate real figures (a mismatch "
                "or an un-validated criterion is release-blocking)."
            ),
            "findings": [],
            "release_blocking": False,
            "checks": [
                {
                    "name": "Household rollup total", "category": "ROLLUP",
                    "expected": "875000.00", "actual": "875000.00", "variance": "0.00",
                    "tolerance": "0.00", "within_tolerance": True, "passed": True,
                    "materiality": "none", "severity": "MINOR",
                    "regulatory_basis": _FIN_REG["ROLLUP"], "source": "illustrative",
                },
                {
                    "name": "GBP rounding half-up 2dp", "category": "ROUNDING",
                    "expected": "1250.00", "actual": "1250.00", "variance": "0.00",
                    "tolerance": "0.01", "within_tolerance": True, "passed": True,
                    "materiality": "none", "severity": "MINOR",
                    "regulatory_basis": _FIN_REG["ROUNDING"], "source": "illustrative",
                },
            ],
            "reconciliation": {
                "total": 2, "passed": 2, "failed": 0, "within_tolerance": 2,
                "total_variance": "0.00",
            },
            "not_validated": [],
        }

    checks = []
    total_var = 0.0
    for c in raw:
        name = c.get("name", "check")
        cat = _fin_category(name)
        exp, act = c.get("expected"), c.get("actual")
        e, a = _num(exp), _num(act)
        tol = 0.01 if cat == "ROUNDING" else 0.00
        if e is not None and a is not None:
            var = round(abs(e - a), 2)
            total_var += var
            variance = f"{var:.2f}"
            within = var <= tol
            passed = within
            materiality = (
                f"£{variance} discrepancy on {cat.lower()}" if var > 0 else "none"
            )
        else:
            variance = "N/A"
            within = bool(c.get("passed"))
            passed = bool(c.get("passed"))
            materiality = "none" if passed else "unquantified — actual not produced"
        checks.append(
            {
                "name": name,
                "category": cat,
                "expected": str(exp),
                "actual": str(act),
                "variance": variance,
                "tolerance": f"{tol:.2f}",
                "within_tolerance": within,
                "passed": passed,
                "materiality": materiality,
                "severity": "BLOCKER" if not passed else "MINOR",
                "regulatory_basis": _FIN_REG[cat],
                "source": "Finance reconciliation extract",
            }
        )

    # Missing evidence: financial AC with no matching check.
    required = [c for c in _ac(story) if any(t in c.lower() for t in _FIN_TERMS)]
    not_validated = [
        ac
        for ac in required
        if not any(_sig_words(ac) & _sig_words(chk["name"]) for chk in checks)
    ]

    failed = [c for c in checks if not c["passed"]]
    blocking = bool(failed or not_validated)
    within_count = sum(1 for c in checks if c["within_tolerance"])

    return {
        "verdict": "FAIL" if blocking else "PASS",
        "summary": (
            f"{len(checks)} financial check(s){note}: {len(checks) - len(failed)} passed, "
            f"{len(failed)} failed. "
            + (
                f"⚠ {len(failed)} failure(s) + {len(not_validated)} un-validated "
                "criterion(s) — release-blocking, no override."
                if blocking
                else "All checks reconcile within tolerance."
            )
        ),
        "findings": [
            {
                "title": f"Integrity check failed: {c['name']}",
                "detail": f"expected {c['expected']}, got {c['actual']} "
                f"(variance {c['variance']}, tolerance {c['tolerance']}); {c['materiality']}",
                "severity": "CRITICAL",
            }
            for c in failed
        ]
        + [
            {
                "title": "Financial criterion not validated",
                "detail": f"No check evidences: {ac}",
                "severity": "HIGH",
            }
            for ac in not_validated
        ],
        "release_blocking": blocking,  # engine re-enforces regardless
        "checks": checks,
        "reconciliation": {
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "within_tolerance": within_count,
            "total_variance": f"{round(total_var, 2):.2f}",
        },
        "not_validated": not_validated,
    }


def regression_scope(story: Story, artifacts=None, upstream=None) -> dict:
    meta = _parsed(artifacts, "METADATA")
    components = (meta or {}).get("components", []) if meta else []
    note = _artifact_note(artifacts, "METADATA")

    bdd = _upstream_output(upstream, "bdd_generator")
    bdd_scenarios = (bdd or {}).get("scenarios", []) if bdd else []

    def _tests_with_tag(tag: str) -> list[str]:
        return [s.get("title", "") for s in bdd_scenarios if tag in (s.get("tags") or [])]

    fca_tests = _tests_with_tag("@fca") or ["FCA-evidence scenarios"]
    regression_tests = _tests_with_tag("@regression") or ["Rollup regression suite"]

    fsc_comps = [c for c in components if "rollup" in c.lower() or "financial" in c.lower()] or components[:2]
    trigger_comps = [c for c in components if "trigger" in c.lower()] or []

    areas = [
        {
            "cloud": "FSC",
            "area": "Household rollup recalculation suite",
            "driving_components": fsc_comps,
            "dependency_type": "ROLLUP_CONFIG",
            "reason": "Directly changed rollup logic — highest financial/regulatory exposure.",
            "priority": "HIGH",
            "effort": "~12 test cases, 2h",
            "suggested_tests": (fca_tests + regression_tests)[:3],
        },
        {
            "cloud": "FSC",
            "area": "Financial-account trigger regression",
            "driving_components": trigger_comps or fsc_comps,
            "dependency_type": "AUTOMATION",
            "reason": "Shares the trigger handler touched by this story.",
            "priority": "HIGH",
            "effort": "~8 test cases, 1.5h",
            "suggested_tests": regression_tests[:2],
        },
        {
            "cloud": "SALES",
            "area": "Person-account sync smoke test",
            "driving_components": fsc_comps,
            "dependency_type": "INTEGRATION",
            "reason": "Household changes ripple into Sales person accounts via sync.",
            "priority": "MEDIUM",
            "effort": "~4 test cases, 0.5h",
            "suggested_tests": ["@smoke person-account sync"],
        },
    ]
    excluded = [
        {
            "area": "Marketing Cloud journeys",
            "reason": "No consent/journey metadata changed by this story.",
        },
        {
            "area": "Full FSC regression",
            "reason": "Change is isolated to rollup logic; full regression not warranted.",
        },
    ]
    priorities = [a["priority"] for a in areas]
    clouds = sorted(set(a["cloud"] for a in areas))
    return {
        "verdict": "PASS",
        "summary": (
            f"Targeted regression: {len(areas)} area(s) across {len(clouds)} cloud(s)"
            f"{note} ({priorities.count('HIGH')} high). Full regression excluded — "
            f"{len(excluded)} area(s) safely out of scope."
        ),
        "findings": [],
        "release_blocking": False,
        "recommended_areas": areas,
        "excluded": excluded,
        "scope_summary": {
            "high": priorities.count("HIGH"),
            "medium": priorities.count("MEDIUM"),
            "low": priorities.count("LOW"),
            "clouds": clouds,
            "total_effort": "~24 test cases, 4h",
        },
    }


def integration_e2e_journey(story: Story, artifacts=None, upstream=None) -> dict:
    junit = _parsed(artifacts, "JUNIT")
    note = _artifact_note(artifacts, "JUNIT")
    failed = int((junit or {}).get("failed", 0)) if junit else 0
    journeys = [
        {
            "name": "New household onboarding rolls up to client balance",
            "clouds": ["FSC", "SALES"],
            "steps": [
                "Create household in FSC",
                "Add active + closed financial accounts",
                "Person-account sync fires to Sales",
                "Household total recalculates and displays",
            ],
            "integration_points": ["FSC→Sales person-account sync", "Rollup trigger"],
            "status": "FAIL" if failed else "PASS",
            "risk": "HIGH",
            "notes": "Financial figure crosses the FSC→Sales boundary." if not failed
            else "Rollup did not reconcile after sync — cross-cloud defect.",
        },
        {
            "name": "Household change triggers a Marketing journey",
            "clouds": ["FSC", "MARKETING"],
            "steps": [
                "Update household composition in FSC",
                "Consent + eligibility evaluated",
                "Marketing Cloud journey enrolment",
            ],
            "integration_points": ["FSC→Marketing enrolment", "Consent check"],
            "status": "NOT_RUN",
            "risk": "MEDIUM",
            "notes": "No consent/journey change in this story — smoke only.",
        },
    ]
    covered = sum(1 for j in journeys if j["status"] in ("PASS", "FAIL"))
    total = sum(len(j["integration_points"]) for j in journeys)
    verdict = "FAIL" if failed else ("WARN" if any(j["status"] == "NOT_RUN" for j in journeys) else "PASS")
    return {
        "verdict": verdict,
        "summary": (
            f"{len(journeys)} cross-cloud journey(s){note}: "
            + ", ".join(f"{j['name'][:32]}… {j['status']}" for j in journeys)
        ),
        "findings": [
            {"title": f"E2E journey failed: {j['name']}", "detail": j["notes"], "severity": "HIGH"}
            for j in journeys if j["status"] == "FAIL"
        ],
        "release_blocking": False,
        "journeys": journeys,
        "covered_integration_points": covered,
        "total_integration_points": total,
    }


def defect_triage(story: Story, artifacts=None, upstream=None) -> dict:
    junit = _parsed(artifacts, "JUNIT")
    te = _upstream_output(upstream, "test_execution_analyst")
    failures = (junit or {}).get("failures", []) if junit else []
    total_failures = len(failures) or int((te or {}).get("run_summary", {}).get("failed", 0) or 0)

    clusters = []
    suggested = []
    if failures:
        # Cluster the classic "governor limit under bulk" signature.
        bulk = [f["name"] for f in failures if "bulk" in (f.get("message", "") + f.get("name", "")).lower()
                or "soql" in (f.get("message", "")).lower() or "limit" in (f.get("message", "")).lower()]
        others = [f["name"] for f in failures if f["name"] not in bulk]
        if bulk:
            clusters.append({
                "signature": "System.LimitException: Too many SOQL queries",
                "tests": bulk,
                "classification": "PRODUCT_DEFECT",
                "suspected_root_cause": "SOQL query inside a loop in the rollup recalculation.",
                "suspected_component": "HouseholdRollupService.recalculate",
                "severity": "CRITICAL",
            })
            suggested.append({
                "title": "Rollup breaches SOQL governor limit under bulk load",
                "severity": "CRITICAL",
                "component": "HouseholdRollupService",
                "from_cluster": "System.LimitException: Too many SOQL queries",
                "recommended_action": "Bulkify: move the SOQL outside the loop; add a 200-record test.",
            })
        if others:
            clusters.append({
                "signature": "UI locator not found",
                "tests": others,
                "classification": "TEST_DEFECT",
                "suspected_root_cause": "Stale selector after a component rename.",
                "suspected_component": "householdSummary LWC test",
                "severity": "MINOR",
            })
    flaky_count = sum(1 for c in clusters if c["classification"] == "FLAKY")
    has_product = any(c["classification"] == "PRODUCT_DEFECT" for c in clusters)
    verdict = "FAIL" if any(c["severity"] in ("BLOCKER", "CRITICAL") and c["classification"] == "PRODUCT_DEFECT" for c in clusters) \
        else ("WARN" if has_product or clusters else "PASS")
    return {
        "verdict": verdict,
        "summary": (
            f"{total_failures} failure(s) triaged into {len(clusters)} cluster(s); "
            f"{len(suggested)} defect(s) suggested."
            if clusters else "No failures to triage — all tests passing."
        ),
        "findings": [
            {"title": d["title"], "detail": d["recommended_action"], "severity": "HIGH"}
            for d in suggested
        ],
        "release_blocking": False,
        "clusters": clusters,
        "suggested_defects": suggested,
        "total_failures": total_failures,
        "flaky_count": flaky_count,
    }


def security_dast(story: Story, artifacts=None) -> dict:
    sarif = _parsed(artifacts, "SARIF")
    note = _artifact_note(artifacts, "SARIF")
    findings = []
    if sarif and sarif.get("findings"):
        for f in sarif["findings"][:6]:
            findings.append({
                "name": f.get("rule", "finding"),
                "severity": _LEVEL_TO_SEV.get(f.get("level"), "MEDIUM"),
                "endpoint": f.get("location") or "/portal",
                "owasp": "A05:2021 Security Misconfiguration",
                "cwe": None,
                "evidence": f.get("message") or "",
                "remediation": "Review and remediate the flagged runtime behaviour.",
                "confidence": "MEDIUM",
            })
    # FSC portal runtime checklist the scanner may not cover.
    findings.append({
        "name": "IDOR on client record endpoint",
        "severity": "HIGH",
        "endpoint": "/services/apexrest/household/{id}",
        "owasp": "A01:2021 Broken Access Control",
        "cwe": "CWE-639",
        "evidence": "Adviser A could request adviser B's household id and receive data.",
        "remediation": "Enforce record-level sharing + WITH SECURITY_ENFORCED on the REST handler.",
        "confidence": "HIGH",
    })
    findings.append({
        "name": "Missing security headers on Experience Cloud portal",
        "severity": "MEDIUM",
        "endpoint": "/s/",
        "owasp": "A05:2021 Security Misconfiguration",
        "cwe": "CWE-693",
        "evidence": "No Content-Security-Policy / HSTS on portal responses.",
        "remediation": "Set CSP, HSTS and X-Content-Type-Options via the CSP settings.",
        "confidence": "HIGH",
    })
    counts = {
        "critical": sum(1 for f in findings if f["severity"] == "CRITICAL"),
        "high": sum(1 for f in findings if f["severity"] == "HIGH"),
        "medium": sum(1 for f in findings if f["severity"] == "MEDIUM"),
        "low": sum(1 for f in findings if f["severity"] == "LOW"),
    }
    if counts["critical"]:
        risk, verdict = "CRITICAL", "FAIL"
    elif counts["high"]:
        risk, verdict = "HIGH", "FAIL"
    elif counts["medium"]:
        risk, verdict = "MEDIUM", "WARN"
    else:
        risk, verdict = "LOW", "PASS"
    return {
        "verdict": verdict,
        "summary": (
            f"DAST triage{note or ' (FSC portal checklist)'}: {len(findings)} finding(s), "
            f"risk {risk} ({counts['high']} high, {counts['medium']} medium)."
        ),
        "findings": [
            {"title": f["name"], "detail": f"{f['endpoint']} — {f['owasp']}", "severity": f["severity"]}
            for f in findings if f["severity"] in ("HIGH", "CRITICAL")
        ][:5],
        "release_blocking": False,
        "security_findings": findings,
        "scanned_target": "wealth-portal.example.com (Experience Cloud)",
        "risk_rating": risk,
        "counts": counts,
    }


def uat_test_design(story: Story, artifacts=None, upstream=None) -> dict:
    criteria = _ac(story)
    cases = []
    for i, c in enumerate(criteria, 1):
        cases.append({
            "id": f"UAT-{story.jira_key}-{i:02d}",
            "title": f"Verify: {c[:70]}",
            "persona": "Adviser" if i % 2 else "Paraplanner",
            "steps": [
                "Log in to the wealth portal as the persona",
                "Open the client's household summary",
                "Perform the action described by the acceptance criterion",
            ],
            "expected_result": f"The system behaves per the criterion: {c[:80]}",
            "ac_ref": c[:80],
            "priority": "P1" if _is_fca_criterion(c) else "P2",
        })
    fca_high = (story.fca_impact.value if story.fca_impact else "HIGH") == "HIGH"
    roles = ["Product Owner", "Business Stakeholder"] + (["Compliance Officer"] if fca_high else [])
    return {
        "verdict": "PASS" if cases else "WARN",
        "summary": (
            f"{len(cases)} UAT case(s) designed for {story.jira_key}, covering "
            f"{len(cases)}/{len(criteria)} acceptance criteria. Sign-off: {', '.join(roles)}."
        ),
        "findings": [],
        "release_blocking": False,
        "test_cases": cases,
        "sign_off_roles": roles,
        "ac_covered": len(cases),
        "ac_total": len(criteria),
    }


def test_data_management(story: Story, artifacts=None) -> dict:
    meta = _parsed(artifacts, "METADATA")
    note = _artifact_note(artifacts, "METADATA")
    fixtures = [
        {
            "name": "Household with mixed-status accounts",
            "purpose": "Rollup includes active, excludes closed/pending",
            "records": "1 household + 200 financial accounts (active/closed/pending)",
            "masking": "SYNTHETIC",
            "compliance_note": "Fully synthetic — no real client data.",
        },
        {
            "name": "Boundary + rounding balances",
            "purpose": "GBP rounding (half-up, 2dp) and boundary totals",
            "records": "12 accounts at rounding boundaries (…005, …004)",
            "masking": "SYNTHETIC",
            "compliance_note": "Fully synthetic.",
        },
        {
            "name": "Vulnerable-customer flagged household",
            "purpose": "Consumer Duty support-path handling",
            "records": "1 household with a vulnerable-customer marker",
            "masking": "SYNTHETIC",
            "compliance_note": "Synthetic marker only; no real vulnerability data.",
        },
    ]
    pii = ["Contact.FirstName/LastName", "Contact.BirthDate", "NationalInsuranceNumber__c",
           "FinancialAccount.AccountNumber", "Account.BillingAddress"]
    return {
        "verdict": "PASS",
        "summary": (
            f"{len(fixtures)} synthetic fixture(s) specified for {story.jira_key}{note}; "
            f"{len(pii)} PII field(s) flagged for synthesis. No real client data required."
        ),
        "findings": [],
        "release_blocking": False,
        "fixtures": fixtures,
        "pii_flags": pii,
        "all_synthetic": True,
    }


# --- Phase 4: Release (no artifact consumers) ---------------------------


def release_readiness(story: Story, artifacts=None) -> dict:
    return {
        "verdict": "WARN",
        "summary": (
            f"{story.jira_key} is close to release-ready; Apex coverage is the one "
            "outstanding item. All FCA and financial checks are green."
        ),
        "findings": [],
        "release_blocking": False,
        "checklist": [
            {"item": "Gate 1 — Refinement signed off", "status": "COMPLETE", "notes": "PO + QE"},
            {"item": "Gate 2 — Development signed off", "status": "COMPLETE", "notes": "Tech Lead"},
            {"item": "AC coverage confirmed", "status": "COMPLETE", "notes": "All criteria mapped"},
            {"item": "Apex coverage >= 85%", "status": "INCOMPLETE", "notes": "Merge drafted tests"},
            {"item": "No open HIGH/CRITICAL static issues", "status": "COMPLETE", "notes": "Currency typing fixed"},
            {"item": "Zero open FCA-scenario failures", "status": "COMPLETE", "notes": "None"},
            {"item": "Financial data integrity passed", "status": "COMPLETE", "notes": "Checks reconcile"},
            {"item": "Regression scope executed", "status": "COMPLETE", "notes": "Targeted suite green"},
        ],
        "evidence_gaps": ["Apex coverage short of org policy — merge drafted tests"],
    }


def uat_signoff_coordinator(story: Story, artifacts=None) -> dict:
    high = story.fca_impact is None or story.fca_impact.value == "HIGH"
    approvals = [
        {"role": "Product Owner", "required_because": "Always required for UAT sign-off"},
        {"role": "Business Stakeholder", "required_because": "Always required — affected business function"},
    ]
    if high:
        approvals.append(
            {
                "role": "Compliance Officer",
                "required_because": f"FCA impact is {_fca(story)} — Compliance sign-off mandatory",
            }
        )
    return {
        "verdict": "PASS",
        "summary": (
            f"{len(approvals)} approvals required for {story.jira_key} "
            + ("(including Compliance, FCA impact HIGH)." if high else "(standard set).")
        ),
        "findings": [],
        "release_blocking": False,
        "required_approvals": approvals,
        "coordination_notes": (
            "Show the PO the UAT results and the household 360 demo; show Compliance "
            "the financial-integrity confirmation and the FCA-scenario evidence. "
            "Collect PO first, then Business, then Compliance."
        ),
    }


def regulatory_audit_trail(story: Story, artifacts=None) -> dict:
    return {
        "verdict": "PASS",
        "summary": (
            f"Release audit narrative drafted for {story.jira_key}. All sections are "
            "supported by the platform's hash-chained evidence pack."
        ),
        "findings": [],
        "release_blocking": False,
        "report_sections": [
            {"section": "Change summary", "content": f"{story.summary} — FCA impact {_fca(story)}, {_cloud(story)}."},
            {"section": "Control execution", "content": "Four-gate HITL process executed: each agent explicitly approved and accepted by a named user; each gate signed with rationale."},
            {"section": "Regulatory testing evidence", "content": "FCA-scenario suite passed; financial data integrity reconciled; release-blocking rules held with no override."},
            {"section": "Approvals", "content": "PO, Business Stakeholder and Compliance Officer sign-offs collected per the HIGH-impact UAT policy."},
            {"section": "Traceability", "content": "Every step is a hash-chained append-only audit event; the chain verifies and the evidence pack is attached to the release ticket."},
        ],
        "completeness_confirmed": True,
    }


GENERATORS = {
    "story_quality": story_quality,
    "fca_regulatory_impact": fca_regulatory_impact,
    "consumer_duty_mapper": consumer_duty_mapper,
    "compliance_ac_advisor": compliance_ac_advisor,
    "three_amigos": three_amigos,
    "bdd_generator": bdd_generator,
    "ac_compliance": ac_compliance,
    "apex_coverage": apex_coverage,
    "static_analysis": static_analysis,
    "code_review": code_review,
    "deployability_validation": deployability_validation,
    "test_execution_analyst": test_execution_analyst,
    "financial_data_integrity": financial_data_integrity,
    "regression_scope": regression_scope,
    "integration_e2e_journey": integration_e2e_journey,
    "defect_triage": defect_triage,
    "security_dast": security_dast,
    "uat_test_design": uat_test_design,
    "test_data_management": test_data_management,
    "release_readiness": release_readiness,
    "uat_signoff_coordinator": uat_signoff_coordinator,
    "regulatory_audit_trail": regulatory_audit_trail,
}


def build(
    agent_key: str, story: Story, guidance: str | None, artifacts=None, upstream=None
) -> dict:
    gen = GENERATORS[agent_key]
    # Agents that consume upstream output take a third arg.
    if agent_key in AGENT_UPSTREAM_INPUTS:
        body = gen(story, artifacts, upstream)
    else:
        body = gen(story, artifacts)
    if guidance:
        # Reflect the reviewer's guidance so the re-run diff view is meaningful.
        body["summary"] = (
            f"Re-run addressing reviewer guidance — “{guidance}”. " + body["summary"]
        )
        body.setdefault("findings", []).insert(
            0,
            {
                "title": "Re-run guidance addressed",
                "detail": f"This attempt specifically incorporated: {guidance}",
                "severity": "LOW",
            },
        )
    return body
