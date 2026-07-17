"""The one calibrated severity scale + its cross-agent ordering."""

from app.services.agents.output_schemas import (
    SEVERITY_ORDER,
    Severity,
    severity_rank,
)
from app.services import referee


def test_canonical_scale_is_five_levels():
    assert list(Severity.__args__) == ["BLOCKER", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
    assert SEVERITY_ORDER == ["LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKER"]


def test_rank_is_strictly_ordered():
    ranks = [severity_rank(s) for s in ["LOW", "MEDIUM", "HIGH", "CRITICAL", "BLOCKER"]]
    assert ranks == sorted(ranks) and len(set(ranks)) == 5
    assert severity_rank("BLOCKER") > severity_rank("CRITICAL") > severity_rank("HIGH")


def test_legacy_defect_aliases_fold_in():
    # MAJOR/MINOR (the old defect vocabulary) map onto the canonical scale.
    assert severity_rank("MAJOR") == severity_rank("HIGH")
    assert severity_rank("MINOR") == severity_rank("LOW")


def test_unknown_and_none_are_zero():
    assert severity_rank(None) == 0
    assert severity_rank("NONE") == 0
    assert severity_rank("bogus") == 0


class _R:
    def __init__(self, phase, findings):
        from app.models import Phase
        self.phase = Phase.TESTING
        self.output_json = {
            "verdict": "WARN", "release_blocking": False,
            "confidence": {"level": "HIGH"}, "summary": "s", "findings": findings,
        }


def test_referee_worst_finding_severity_across_agents():
    latest = {
        "a": _R("t", [{"title": "x", "detail": "y", "severity": "MEDIUM"}]),
        "b": _R("t", [{"title": "x", "detail": "y", "severity": "CRITICAL"},
                      {"title": "z", "detail": "w", "severity": "LOW"}]),
    }
    h = referee.compute_health(latest)
    # The single worst finding across both agents, via the unified rank.
    assert h["worst_finding_severity"] == "CRITICAL"
