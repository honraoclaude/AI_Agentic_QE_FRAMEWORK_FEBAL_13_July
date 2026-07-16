"""Human-feedback loop / agent-performance analytics.

Mines the human decisions the platform already records — Accept, Reject (+reason),
and Re-run-with-guidance — to surface, per agent: how often humans agree with it,
how often they push back, why, and a derived trust score. This is the learning /
defensibility layer: "we measure how often each agent's output is accepted vs
overridden, and act on it." Pure reads — no model calls.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, RunStatus
from .agents.registry import AGENTS, get_agent

# Runs that reached a human decision.
_DECIDED = {RunStatus.ACCEPTED, RunStatus.REJECTED}


def _agent_meta(key: str):
    try:
        a = get_agent(key)
        return a.name, a.phase.value
    except KeyError:
        return key, "?"


async def agent_performance(session: AsyncSession) -> dict:
    runs = (await session.execute(select(AgentRun))).scalars().all()

    # agent_key -> accumulator
    stats: dict[str, dict] = {}

    def acc(key: str) -> dict:
        return stats.setdefault(key, {
            "accepted": 0, "rejected": 0, "reruns": 0,
            "verdicts": {"PASS": 0, "WARN": 0, "FAIL": 0},
            "reject_reasons": [], "guidance": [], "attempts_by_story": {},
        })

    for r in runs:
        a = acc(r.agent_key)
        if r.status == RunStatus.ACCEPTED:
            a["accepted"] += 1
        elif r.status == RunStatus.REJECTED:
            a["rejected"] += 1
            if r.decision_reason:
                a["reject_reasons"].append(r.decision_reason)
        if r.parent_run_id:  # this run is a re-run of a prior attempt
            a["reruns"] += 1
            if r.guidance:
                a["guidance"].append(r.guidance)
        if r.output_json and r.output_json.get("verdict") in a["verdicts"]:
            a["verdicts"][r.output_json["verdict"]] += 1
        # track max attempt per (story) to compute avg attempts-to-accept
        prev = a["attempts_by_story"].get(r.story_id, 0)
        a["attempts_by_story"][r.story_id] = max(prev, r.attempt)

    agents = []
    for key, a in stats.items():
        name, phase = _agent_meta(key)
        decided = a["accepted"] + a["rejected"]
        pushback = a["rejected"] + a["reruns"]
        denom = a["accepted"] + pushback
        acceptance_rate = round(a["accepted"] / decided, 3) if decided else None
        override_rate = round(pushback / denom, 3) if denom else 0.0
        trust_score = round(100 * a["accepted"] / denom) if denom else None
        attempts = list(a["attempts_by_story"].values())
        avg_attempts = round(sum(attempts) / len(attempts), 2) if attempts else None
        agents.append({
            "agent_key": key, "agent_name": name, "phase": phase,
            "accepted": a["accepted"], "rejected": a["rejected"], "reruns": a["reruns"],
            "decided": decided,
            "acceptance_rate": acceptance_rate,
            "override_rate": override_rate,
            "trust_score": trust_score,
            "avg_attempts": avg_attempts,
            "verdicts": a["verdicts"],
            "reject_reasons": a["reject_reasons"][:5],
            "guidance_samples": a["guidance"][:5],
        })

    # Rank: lowest trust / highest override first (most human pushback).
    ranked = sorted(
        [x for x in agents if x["trust_score"] is not None],
        key=lambda x: (x["trust_score"], -x["override_rate"]),
    )
    agents.sort(key=lambda x: (x["phase"], x["agent_name"]))

    total_accepted = sum(a["accepted"] for a in agents)
    total_rejected = sum(a["rejected"] for a in agents)
    total_reruns = sum(a["reruns"] for a in agents)
    total_decided = total_accepted + total_rejected

    return {
        "agents": agents,
        "summary": {
            "agents_defined": len(AGENTS),
            "agents_with_data": len([a for a in agents if a["decided"] or a["reruns"]]),
            "total_accepted": total_accepted,
            "total_rejected": total_rejected,
            "total_reruns": total_reruns,
            "overall_acceptance_rate": round(total_accepted / total_decided, 3) if total_decided else None,
        },
        "needs_attention": ranked[:5],
    }
