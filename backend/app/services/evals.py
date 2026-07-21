"""Agent eval harness — measured accuracy against expert-labelled golden cases.

Prompt versions were previously bumped on judgement alone; this harness makes
them measured. Each agent has golden cases (backend/evals/golden/<agent>.json):
an input (story + artifacts + upstream) and expert-labelled expectations over
the structured output, graded deterministically:

- equals        — exact value at a dot-path
- approx/tol    — numeric within tolerance (financial variances)
- min_len       — a list must have at least N items
- contains      — a string field must contain a substring
- not_contains  — a string field must NOT contain a substring (regression
                  guards: "the fixed bug's wording must never come back")
- set_overlap   — a list field must include at least `min` (0-1, default 1.0)
                  fraction of an expected set (citations, finding names —
                  where exact order/count don't matter but coverage does)

Runs against the demo path in CI (deterministic — catches fixture/schema
regressions on every push) and against the real Claude path when an API key is
present (measures actual model accuracy per prompt version). Same cases, same
grading — the scorecard is comparable across both.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..models.enums import Cloud, FcaImpact, Phase
from .agents.demo_outputs import build
from .agents.output_schemas import OUTPUT_SCHEMAS

# .../backend/app/services/evals.py -> parents[2] == backend/
GOLDEN_DIR = Path(__file__).resolve().parents[2] / "evals" / "golden"


def story_shim(spec: dict) -> SimpleNamespace:
    """A Story-shaped object built from a golden case (no DB involved)."""
    fca = spec.get("fca_impact")
    cloud = spec.get("cloud")
    return SimpleNamespace(
        jira_key=spec.get("jira_key", "EVAL-1"),
        summary=spec.get("summary", ""),
        description=spec.get("description", ""),
        acceptance_criteria=spec.get("acceptance_criteria", []),
        story_points=spec.get("story_points"),
        sprint=spec.get("sprint"),
        labels=spec.get("labels", []),
        priority=spec.get("priority"),
        fca_impact=FcaImpact(fca) if fca else None,
        fca_impact_confirmed=bool(spec.get("fca_impact_confirmed")),
        cloud=Cloud(cloud) if cloud else None,
        current_phase=Phase(spec.get("current_phase", "TESTING")),
    )


def _at_path(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def grade(output: dict, expectations: list[dict]) -> list[dict]:
    results = []
    for exp in expectations:
        path = exp["path"]
        actual = _at_path(output, path)
        ok, want = True, None
        if "equals" in exp:
            want = exp["equals"]
            ok = actual == want
        elif "approx" in exp:
            want = exp["approx"]
            tol = exp.get("tol", 0.01)
            try:
                ok = abs(float(actual) - float(want)) <= tol
            except (TypeError, ValueError):
                ok = False
        elif "min_len" in exp:
            want = f"len>={exp['min_len']}"
            ok = isinstance(actual, list) and len(actual) >= exp["min_len"]
        elif "contains" in exp:
            want = exp["contains"]
            ok = isinstance(actual, str) and want.lower() in actual.lower()
        elif "not_contains" in exp:
            want = f"NOT: {exp['not_contains']}"
            ok = isinstance(actual, str) and exp["not_contains"].lower() not in actual.lower()
        elif "set_overlap" in exp:
            expected_set = set(exp["set_overlap"])
            min_frac = exp.get("min", 1.0)
            want = f"{min_frac:.0%} of {sorted(expected_set)}"
            actual_set = set(actual) if isinstance(actual, list) else set()
            overlap = len(expected_set & actual_set) / len(expected_set) if expected_set else 1.0
            ok = overlap >= min_frac
        results.append({"path": path, "expected": want, "actual": actual, "passed": ok})
    return results


def load_cases(agent_key: str) -> list[dict]:
    f = GOLDEN_DIR / f"{agent_key}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))["cases"]


def run_agent_evals(agent_key: str) -> dict:
    """Execute every golden case for an agent on the demo path and grade it.
    The output is also schema-validated — a structural regression fails red."""
    cases = load_cases(agent_key)
    results = []
    for case in cases:
        story = story_shim(case.get("story", {}))
        output = build(
            agent_key, story, None,
            artifacts=case.get("artifacts", []),
            upstream=case.get("upstream", []),
        )
        OUTPUT_SCHEMAS[agent_key].model_validate(output)  # structural gate
        checks = grade(output, case["expect"])
        results.append({
            "case": case["name"],
            "passed": all(c["passed"] for c in checks),
            "checks": checks,
        })
    return {
        "agent_key": agent_key,
        "cases": len(results),
        "passed": sum(1 for r in results if r["passed"]),
        "failed": sum(1 for r in results if not r["passed"]),
        "results": results,
    }


def available_agents() -> list[str]:
    if not GOLDEN_DIR.exists():
        return []
    return sorted(p.stem for p in GOLDEN_DIR.glob("*.json"))


def scorecard() -> dict:
    """The eval harness's own status, live: every agent with a golden file,
    graded now against the demo path. This IS the regression gate CI would
    run — surfaced here so it's visible in the running app, not just pytest."""
    from .agents.registry import AGENTS

    agents = []
    for key in available_agents():
        card = run_agent_evals(key)
        agents.append({
            "agent_key": key,
            "agent_name": AGENTS[key].name if key in AGENTS else key,
            "cases": card["cases"],
            "passed": card["passed"],
            "failed": card["failed"],
            "failing_cases": [
                {
                    "case": r["case"],
                    "failing_checks": [c for c in r["checks"] if not c["passed"]],
                }
                for r in card["results"]
                if not r["passed"]
            ],
        })
    covered = len(agents)
    total_agents = len(AGENTS)
    return {
        "agents": agents,
        "summary": {
            "agents_with_golden_data": covered,
            "agents_total": total_agents,
            "coverage_percent": round(covered / total_agents * 100, 1) if total_agents else 0.0,
            "total_cases": sum(a["cases"] for a in agents),
            "total_passed": sum(a["passed"] for a in agents),
            "total_failed": sum(a["failed"] for a in agents),
        },
    }
