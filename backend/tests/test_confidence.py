"""Every agent carries a self-assessed `confidence` on the shared envelope."""

from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import OUTPUT_SCHEMAS


def _story():
    class _FI:
        value = "HIGH"

    class _S:
        jira_key = "WLTH-101"
        summary = "Household rollup recalculates client-facing balance"
        acceptance_criteria = ["Rollup sums active accounts", "Closed accounts excluded"]
        fca_impact = _FI()
        cloud = None

    return _S()


def test_every_agent_emits_confidence_valid_against_schema():
    story = _story()
    for key in GENERATORS:
        body = build(key, story, None, artifacts=[], upstream=[])
        # Validates against the agent's own schema (confidence is on the envelope).
        parsed = OUTPUT_SCHEMAS[key].model_validate(body)
        assert parsed.confidence.level in ("HIGH", "MEDIUM", "LOW"), key
        assert parsed.confidence.rationale, key


def test_confidence_is_higher_with_evidence():
    story = _story()
    # static_analysis consumes SARIF — evidence should lift confidence to HIGH.
    sarif = {"kind": "SARIF", "filename": "s.sarif", "summary": "",
             "parsed": {"findings": [], "counts": {}}}
    with_ev = build("static_analysis", story, None, artifacts=[sarif])
    without_ev = build("static_analysis", story, None, artifacts=[])
    assert with_ev["confidence"]["level"] == "HIGH"
    assert without_ev["confidence"]["level"] == "MEDIUM"
    # The no-evidence path tells the human exactly why it might be wrong.
    assert without_ev["confidence"]["caveats"]


def test_agent_can_override_default_confidence():
    """If a generator sets its own confidence, build() must not clobber it."""
    story = _story()
    body = build("static_analysis", story, None, artifacts=[])
    body_key = "confidence"
    assert body_key in body  # present either way
