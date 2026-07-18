"""Pipeline DAG projection — the story's agent graph, ready to draw.

A pure read-model over data that already exists: the 26 agents (nodes, by
phase/sequence), the chaining edges (AGENT_UPSTREAM_INPUTS), the artifact
sources feeding consuming agents (AGENT_ARTIFACT_KINDS × the story's uploaded
artifacts), latest run status per agent, and the four gates. No model calls,
no persistence — a projection for the frontend to render as SVG.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AGENT_ARTIFACT_KINDS,
    AGENT_UPSTREAM_INPUTS,
    AgentRun,
    Artifact,
    Gate,
    Story,
)
from .agents.registry import AGENTS


async def build(session: AsyncSession, story: Story) -> dict:
    runs = (
        (await session.execute(select(AgentRun).where(AgentRun.story_id == story.id)))
        .scalars()
        .all()
    )
    latest: dict[str, AgentRun] = {}
    for r in runs:
        cur = latest.get(r.agent_key)
        if cur is None or r.attempt > cur.attempt:
            latest[r.agent_key] = r

    nodes = []
    for a in sorted(AGENTS.values(), key=lambda x: (x.phase.value, x.sequence)):
        run = latest.get(a.key)
        o = (run.output_json or {}) if run else {}
        nodes.append({
            "key": a.key,
            "name": a.name,
            "phase": a.phase.value,
            "sequence": a.sequence,
            "blocking_capable": a.blocking_capable,
            "status": run.status.value if run else None,
            "attempt": run.attempt if run else 0,
            "run_id": run.id if run else None,
            "verdict": o.get("verdict"),
            "confidence": (o.get("confidence") or {}).get("level"),
            "release_blocking": bool(o.get("release_blocking")),
        })

    edges = [
        {"source": up, "target": key, "kind": "upstream"}
        for key, ups in AGENT_UPSTREAM_INPUTS.items()
        for up in ups
        if key in AGENTS and up in AGENTS
    ]

    # Artifact sources actually present on this story -> the agents that
    # consume any of the kinds that source provided.
    artifacts = (
        (await session.execute(select(Artifact).where(Artifact.story_id == story.id)))
        .scalars()
        .all()
    )
    kinds_by_source: dict[str, set] = {}
    for art in artifacts:
        kinds_by_source.setdefault(art.source, set()).add(art.kind)
    sources = []
    for src, kinds in sorted(kinds_by_source.items()):
        sources.append({"id": src, "kinds": sorted(k.value for k in kinds)})
        for agent_key, consumed in AGENT_ARTIFACT_KINDS.items():
            if agent_key in AGENTS and kinds & set(consumed):
                edges.append({
                    "source": f"src:{src}", "target": agent_key, "kind": "artifact",
                })

    gates = (
        (await session.execute(select(Gate).where(Gate.story_id == story.id)))
        .scalars()
        .all()
    )
    gate_status = {
        g.phase.value: {"id": g.id, "status": g.status.value} for g in gates
    }

    return {
        "story_id": story.id,
        "jira_key": story.jira_key,
        "current_phase": story.current_phase.value,
        "nodes": nodes,
        "edges": edges,
        "sources": sources,
        "gates": gate_status,
    }
