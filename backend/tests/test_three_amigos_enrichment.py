"""Three Amigos v3 enrichment: AC-anchored rules, typed example cards, a
verifiable DoD, decision-record agreements, owned/blocking open questions —
and the BDD generator's deterministic every-example-covered check."""

from sqlalchemy import select

from app.models import Story
from app.services import referee
from app.services.agents.demo_outputs import GENERATORS, build
from app.services.agents.output_schemas import (
    BddGeneratorOutput,
    ThreeAmigosOutput,
)
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


async def test_example_cards_are_typed_anchored_and_unique(session, adapter):
    story = await _seed(session, adapter)
    parsed = ThreeAmigosOutput.model_validate(GENERATORS["three_amigos"](story))

    ids = [ex.id for r in parsed.example_map for ex in r.examples]
    assert ids and len(ids) == len(set(ids)), "card ids must be unique"
    assert all(i.startswith("EX-") for i in ids)
    # A typed spread — not everything is a happy-path card.
    kinds = {ex.kind for r in parsed.example_map for ex in r.examples}
    assert {"NEGATIVE", "BOUNDARY"} <= kinds
    # Regulatory-evidence cards are machine-flagged (no string [FCA] convention).
    assert any(ex.fca for r in parsed.example_map for ex in r.examples)
    assert not any("[FCA]" in ex.text for r in parsed.example_map for ex in r.examples)
    # Rules anchor to the acceptance criteria (story has ACs in the demo seed).
    assert any(r.ac_refs for r in parsed.example_map)


async def test_dod_agreements_questions_are_structured(session, adapter):
    story = await _seed(session, adapter)
    parsed = ThreeAmigosOutput.model_validate(GENERATORS["three_amigos"](story))

    # DoD: a checkable contract — items map to verifying agents; FCA flagged.
    verifiers = {d.verified_by for d in parsed.definition_of_done}
    assert "MANUAL" in verifiers and len(verifiers - {"MANUAL"}) >= 3
    assert any(d.fca_evidence for d in parsed.definition_of_done)
    # Agreements carry the audit "why".
    assert all(a.rationale for a in parsed.agreements)
    # Exactly the blocking question the summary calls out.
    blocking = [q for q in parsed.open_questions if q.blocking]
    assert len(blocking) == 1 and blocking[0].owner_persona == "PRODUCT_OWNER"
    # Self-consistency: the DoD no longer pre-asserts an answer (0.00 variance)
    # to the open tolerance question.
    assert not any("0.00 variance" in d.item for d in parsed.definition_of_done)


async def test_bdd_cites_cards_and_flags_uncovered(session, adapter):
    story = await _seed(session, adapter)
    ta = GENERATORS["three_amigos"](story)
    upstream = [{"agent_key": "three_amigos", "agent_name": "Three Amigos", "output": ta}]
    parsed = BddGeneratorOutput.model_validate(
        build("bdd_generator", story, None, artifacts=[], upstream=upstream)
    )

    all_ids = {ex["id"] for r in ta["example_map"] for ex in r["examples"]}
    cited = {ref for s in parsed.scenarios for ref in s.example_refs}
    assert cited and cited <= all_ids, "example_refs must cite real card ids"
    # Deterministic coverage bookkeeping reconciles.
    cov = parsed.coverage
    assert cov.examples_total == len(all_ids)
    assert cov.examples_covered == len(all_ids) - len(cov.uncovered_examples)
    assert set(cov.uncovered_examples) == all_ids - cited
    # The demo intentionally leaves one card uncovered — surfaced as a finding.
    assert cov.uncovered_examples and parsed.findings
    # FCA-flagged cards are realised, and at least one realising scenario is @fca.
    fca_ids = {ex["id"] for r in ta["example_map"] for ex in r["examples"] if ex["fca"]}
    assert fca_ids <= cited, "regulatory-evidence cards must not go uncovered"
    realising = [s for s in parsed.scenarios if set(s.example_refs) & fca_ids]
    assert any("@fca" in s.tags for s in realising)


async def test_bdd_unchained_has_no_example_refs(session, adapter):
    story = await _seed(session, adapter)
    parsed = BddGeneratorOutput.model_validate(
        build("bdd_generator", story, None, artifacts=[], upstream=None)
    )
    assert all(not s.example_refs for s in parsed.scenarios)
    assert parsed.coverage.examples_total == 0
    assert not parsed.coverage.uncovered_examples


class _FakeRun:
    def __init__(self, output):
        from app.models import Phase

        self.phase = Phase.REFINEMENT
        self.output_json = {
            "verdict": "PASS",
            "release_blocking": False,
            "confidence": {"level": "HIGH"},
            "summary": "s",
            "findings": [],
            **output,
        }


def test_referee_flags_bdd_drafted_over_blocking_question():
    latest = {
        "three_amigos": _FakeRun(
            {"open_questions": [{"question": "Tolerance?", "owner_persona": "PRODUCT_OWNER", "blocking": True}]}
        ),
        "bdd_generator": _FakeRun({}),
    }
    rules = {i["rule"] for i in referee.find_inconsistencies(latest)}
    assert "blocking_question_vs_bdd" in rules
    # Not flagged when the question is non-blocking.
    latest["three_amigos"].output_json["open_questions"][0]["blocking"] = False
    rules = {i["rule"] for i in referee.find_inconsistencies(latest)}
    assert "blocking_question_vs_bdd" not in rules


def test_referee_flags_dod_item_whose_verifier_fails():
    latest = {
        "three_amigos": _FakeRun(
            {
                "definition_of_done": [
                    {"item": "Coverage ≥ 85%", "verified_by": "apex_coverage", "fca_evidence": False},
                    {"item": "Runbook updated", "verified_by": "MANUAL", "fca_evidence": False},
                ]
            }
        ),
        "apex_coverage": _FakeRun({"verdict": "FAIL"}),
    }
    issues = referee.find_inconsistencies(latest)
    match = [i for i in issues if i["rule"] == "dod_verifier_failing"]
    assert match and "Coverage" in match[0]["detail"]
    # A passing verifier clears it.
    latest["apex_coverage"].output_json["verdict"] = "PASS"
    assert not [
        i for i in referee.find_inconsistencies(latest) if i["rule"] == "dod_verifier_failing"
    ]
