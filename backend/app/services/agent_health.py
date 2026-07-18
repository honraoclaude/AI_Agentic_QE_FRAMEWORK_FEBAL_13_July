"""Operational Agent Health — the SRE layer over the agent fleet.

Deterministic aggregation over AgentRun rows (no model calls): failure rates,
latency, token spend, and per-prompt-version reliability — the operational
signals the quality analytics (feedback.py) and per-story synthesis
(referee.py) deliberately don't cover.

Answers: is an agent erroring? slowing? burning tokens? did the last prompt
bump regress reliability? Simple threshold alerts; an LLM narrative layer can
come later if ever needed — reproducibility beats cleverness here.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, RunStatus
from .agents.registry import AGENTS

# Alert thresholds — deliberately simple and documented.
FAILURE_RATE_ALERT = 0.25   # ≥25% of executed runs failed (min 3 executed)
MIN_EXECUTED_FOR_ALERT = 3


def _duration_s(run: AgentRun) -> float | None:
    if run.started_at and run.completed_at:
        return max(0.0, (run.completed_at - run.started_at).total_seconds())
    return None


async def compute(session: AsyncSession) -> dict:
    rows = (await session.execute(select(AgentRun))).scalars().all()

    per: dict[str, dict] = {}
    for r in rows:
        a = per.setdefault(r.agent_key, {
            "executed": 0, "failed": 0, "durations": [],
            "tokens_in": 0, "tokens_out": 0, "versions": {},
        })
        executed = r.status in (
            RunStatus.COMPLETED, RunStatus.ACCEPTED, RunStatus.REJECTED,
            RunStatus.RERUN_REQUESTED, RunStatus.FAILED,
        )
        if not executed:
            continue
        a["executed"] += 1
        v = a["versions"].setdefault(r.prompt_version or "?", {"executed": 0, "failed": 0})
        v["executed"] += 1
        if r.status == RunStatus.FAILED:
            a["failed"] += 1
            v["failed"] += 1
            continue
        d = _duration_s(r)
        if d is not None:
            a["durations"].append(d)
        usage = r.token_usage or {}
        a["tokens_in"] += usage.get("input_tokens") or 0
        a["tokens_out"] += usage.get("output_tokens") or 0

    agents, alerts = [], []
    for key, a in per.items():
        defn = AGENTS.get(key)
        durations = a["durations"]
        failure_rate = round(a["failed"] / a["executed"], 3) if a["executed"] else 0.0
        versions = [
            {
                "version": ver,
                "executed": v["executed"],
                "failed": v["failed"],
                "failure_rate": round(v["failed"] / v["executed"], 3) if v["executed"] else 0.0,
            }
            for ver, v in sorted(a["versions"].items())
        ]
        entry = {
            "agent_key": key,
            "agent_name": defn.name if defn else key,
            "phase": defn.phase.value if defn else "?",
            "current_prompt_version": defn.prompt_version if defn else "?",
            "executed": a["executed"],
            "failed": a["failed"],
            "failure_rate": failure_rate,
            "avg_duration_s": round(sum(durations) / len(durations), 2) if durations else None,
            "max_duration_s": round(max(durations), 2) if durations else None,
            "tokens_in": a["tokens_in"],
            "tokens_out": a["tokens_out"],
            "versions": versions,
        }
        agents.append(entry)

        if a["executed"] >= MIN_EXECUTED_FOR_ALERT and failure_rate >= FAILURE_RATE_ALERT:
            alerts.append({
                "agent_key": key,
                "agent_name": entry["agent_name"],
                "kind": "FAILURE_RATE",
                "detail": f"{entry['agent_name']}: {a['failed']}/{a['executed']} "
                f"executed runs failed ({failure_rate:.0%}).",
            })
        # Prompt-version regression: current version reliably worse than the
        # previous one on at least MIN_EXECUTED runs each.
        if len(versions) >= 2:
            prev, cur = versions[-2], versions[-1]
            if (
                cur["executed"] >= MIN_EXECUTED_FOR_ALERT
                and prev["executed"] >= MIN_EXECUTED_FOR_ALERT
                and cur["failure_rate"] >= prev["failure_rate"] + 0.2
            ):
                alerts.append({
                    "agent_key": key,
                    "agent_name": entry["agent_name"],
                    "kind": "VERSION_REGRESSION",
                    "detail": f"{entry['agent_name']}: {cur['version']} fails at "
                    f"{cur['failure_rate']:.0%} vs {prev['version']} at "
                    f"{prev['failure_rate']:.0%} — the prompt bump may have regressed.",
                })

    agents.sort(key=lambda x: (-x["failure_rate"], -(x["executed"])))
    total_exec = sum(x["executed"] for x in agents)
    return {
        "agents": agents,
        "alerts": alerts,
        "summary": {
            "agents_with_runs": len(agents),
            "total_executed": total_exec,
            "total_failed": sum(x["failed"] for x in agents),
            "total_tokens_in": sum(x["tokens_in"] for x in agents),
            "total_tokens_out": sum(x["tokens_out"] for x in agents),
        },
    }
