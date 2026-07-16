"""Refinement regulatory agents: FCA Impact, Consumer Duty, Compliance AC Advisor.

They behave like the other Refinement agents — advisory, non-blocking, chained.
"""

from app.models import AGENT_UPSTREAM_INPUTS, Phase
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    OUTPUT_SCHEMAS,
    ComplianceAcAdvisorOutput,
    ConsumerDutyOutput,
    FcaRegulatoryImpactOutput,
)
from app.services.agents.registry import agents_for_phase


def _story():
    """Minimal stand-in exposing the fields the demo generators read."""

    class _S:
        jira_key = "WLTH-101"
        summary = "Household rollup recalculates client-facing balance"
        acceptance_criteria = ["Rollup sums active accounts", "Closed accounts excluded"]
        fca_impact = None
        cloud = None

    return _S()


# ------------------------------------------------------------------ registry


def test_refinement_has_six_agents_in_order():
    seq = [a.key for a in agents_for_phase(Phase.REFINEMENT)]
    assert seq == [
        "story_quality",
        "fca_regulatory_impact",
        "consumer_duty_mapper",
        "compliance_ac_advisor",
        "three_amigos",
        "bdd_generator",
    ]


def test_regulatory_agents_registered_everywhere():
    for key in ("fca_regulatory_impact", "consumer_duty_mapper", "compliance_ac_advisor"):
        assert key in OUTPUT_SCHEMAS
        assert key in GENERATORS
    # AC Advisor feeds BDD so its criteria reach the @fca scenarios.
    assert "compliance_ac_advisor" in AGENT_UPSTREAM_INPUTS["bdd_generator"]


# ------------------------------------------------------------------ outputs


def test_fca_regulatory_impact_output_valid_and_nonblocking():
    story = _story()
    body = build("fca_regulatory_impact", story, None, artifacts=[], upstream=[])
    parsed = FcaRegulatoryImpactOutput.model_validate(body)
    assert parsed.proposed_fca_impact in ("LOW", "MEDIUM", "HIGH")
    assert parsed.applicable_regulations
    assert any(r.area == "PRIN" for r in parsed.applicable_regulations)  # Consumer Duty
    assert parsed.release_blocking is False


def test_consumer_duty_maps_all_four_outcomes():
    story = _story()
    fca = build("fca_regulatory_impact", story, None, artifacts=[], upstream=[])
    upstream = [{"agent_key": "fca_regulatory_impact", "agent_name": "FCA", "output": fca}]
    body = build("consumer_duty_mapper", story, None, artifacts=[], upstream=upstream)
    parsed = ConsumerDutyOutput.model_validate(body)
    outcomes = {o.outcome for o in parsed.outcomes}
    assert outcomes == {
        "PRODUCTS_AND_SERVICES",
        "PRICE_AND_VALUE",
        "CONSUMER_UNDERSTANDING",
        "CONSUMER_SUPPORT",
    }
    assert parsed.unaddressed_count == sum(
        1 for o in parsed.outcomes if o.status == "NOT_ADDRESSED"
    )
    assert parsed.release_blocking is False


def test_ac_advisor_consumes_duty_gaps_and_proposes_musts():
    story = _story()
    fca = build("fca_regulatory_impact", story, None, artifacts=[], upstream=[])
    duty = build(
        "consumer_duty_mapper", story, None, artifacts=[],
        upstream=[{"agent_key": "fca_regulatory_impact", "agent_name": "FCA", "output": fca}],
    )
    upstream = [
        {"agent_key": "fca_regulatory_impact", "agent_name": "FCA", "output": fca},
        {"agent_key": "consumer_duty_mapper", "agent_name": "CD", "output": duty},
    ]
    body = build("compliance_ac_advisor", story, None, artifacts=[], upstream=upstream)
    parsed = ComplianceAcAdvisorOutput.model_validate(body)
    assert parsed.suggested_criteria
    assert any(c.priority == "MUST" for c in parsed.suggested_criteria)
    assert any(c.regulatory_basis for c in parsed.suggested_criteria)
    # coverage_gaps should reflect the Consumer Duty gaps chained in from upstream.
    duty_gaps = [o.get("gap") for o in duty["outcomes"] if o.get("gap")]
    assert parsed.coverage_gaps == duty_gaps
    assert parsed.release_blocking is False
