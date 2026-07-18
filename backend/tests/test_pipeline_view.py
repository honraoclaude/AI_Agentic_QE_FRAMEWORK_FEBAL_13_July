"""Pipeline DAG projection: nodes for all agents, chaining + artifact edges,
gate statuses — a pure read-model."""

from sqlalchemy import select

from app.models import AGENT_UPSTREAM_INPUTS, Artifact, ArtifactKind, Story
from app.services import pipeline_view, workflow
from app.services.agents.registry import AGENTS
from app.services.jira import sync_service


async def _seed(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


async def test_projection_covers_all_agents_and_edges(session, adapter):
    story = await _seed(session, adapter)
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")

    view = await pipeline_view.build(session, story)
    assert {n["key"] for n in view["nodes"]} == set(AGENTS)
    sq = next(n for n in view["nodes"] if n["key"] == "story_quality")
    assert sq["status"] == "COMPLETED" and sq["verdict"] in ("PASS", "WARN", "FAIL")
    # Never-run agents still appear (status None) — the full pipeline is visible.
    assert any(n["status"] is None for n in view["nodes"])
    # Every upstream pair is an edge; three_amigos wiring included.
    upstream_edges = {(e["source"], e["target"]) for e in view["edges"]
                      if e["kind"] == "upstream"}
    assert ("three_amigos", "bdd_generator") in upstream_edges
    assert ("story_quality", "three_amigos") in upstream_edges
    expected = sum(len(v) for v in AGENT_UPSTREAM_INPUTS.values())
    assert len(upstream_edges) == expected
    # Gates keyed by phase.
    assert "REFINEMENT" in view["gates"]


async def test_artifact_sources_become_feed_edges(session, adapter):
    story = await _seed(session, adapter)
    session.add(Artifact(
        story_id=story.id, kind=ArtifactKind.JUNIT, filename="results.xml",
        content_type="text/xml", size_bytes=10, parsed={}, summary="s",
        uploaded_by="t", source="COPADO",
    ))
    await session.flush()

    view = await pipeline_view.build(session, story)
    assert view["sources"] == [{"id": "COPADO", "kinds": ["JUNIT"]}]
    art_edges = [e for e in view["edges"] if e["kind"] == "artifact"]
    targets = {e["target"] for e in art_edges}
    assert all(e["source"] == "src:COPADO" for e in art_edges)
    # JUNIT consumers per AGENT_ARTIFACT_KINDS.
    assert "test_execution_analyst" in targets and "defect_triage" in targets
    assert "apex_coverage" not in targets  # consumes COVERAGE, not JUNIT
