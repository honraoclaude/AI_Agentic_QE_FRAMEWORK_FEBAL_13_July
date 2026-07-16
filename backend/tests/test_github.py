import pytest
from sqlalchemy import select

from app.models import ArtifactKind, Story
from app.services.artifacts import service as artifact_service
from app.services.github import service as github_service
from app.services.github.mock_adapter import MockGithubAdapter
from app.services.jira import sync_service
from app.services.workflow import NotFoundError


async def _seed_story(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


# ------------------------------------------------------------------ mock adapter


async def test_mock_adapter_returns_expected_kinds():
    items = await MockGithubAdapter().fetch_branch_artifacts("acme/wealth", "feature/WLTH-101")
    kinds = [i.kind for i in items]
    assert ArtifactKind.METADATA in kinds
    assert ArtifactKind.SARIF in kinds
    assert ArtifactKind.JUNIT in kinds
    assert ArtifactKind.COVERAGE in kinds
    assert all("wealth" in i.ref for i in items)


# ------------------------------------------------------------------ connect/sync


async def test_connect_links_branch(session, adapter):
    story = await _seed_story(session, adapter)
    linked = await github_service.connect(
        session, repo="acme/wealth-sfdx", branch="feature/WLTH-101",
        jira_key="WLTH-101", actor="Tech Lead",
    )
    assert linked.github_repo == "acme/wealth-sfdx"
    assert linked.github_branch == "feature/WLTH-101"


async def test_sync_requires_connection(session, adapter):
    story = await _seed_story(session, adapter)
    with pytest.raises(NotFoundError):
        await github_service.sync(session, MockGithubAdapter(), story=story)


async def test_sync_ingests_and_feeds_agents(session, adapter):
    story = await _seed_story(session, adapter)
    await github_service.connect(
        session, repo="acme/wealth-sfdx", branch="feature/WLTH-101", story_id=story.id
    )
    stored = await github_service.sync(session, MockGithubAdapter(), story=story)
    await session.flush()

    assert stored and all(a.source == "GITHUB" for a in stored)
    assert all("wealth-sfdx" in (a.source_ref or "") for a in stored)

    # The SARIF feeds Static Analysis; the METADATA feeds Regression Scope;
    # the JUNIT feeds Test Execution — all as GitHub-sourced evidence.
    sa = await artifact_service.gather_for_agent(session, story.id, "static_analysis")
    assert any(c["kind"] == "SARIF" and c["source"] == "GITHUB" for c in sa)
    rs = await artifact_service.gather_for_agent(session, story.id, "regression_scope")
    assert any(c["kind"] == "METADATA" and c["source"] == "GITHUB" for c in rs)
    te = await artifact_service.gather_for_agent(session, story.id, "test_execution_analyst")
    assert any(c["kind"] == "JUNIT" for c in te)


async def test_sync_metadata_has_components(session, adapter):
    story = await _seed_story(session, adapter)
    await github_service.connect(
        session, repo="acme/wealth-sfdx", branch="main", story_id=story.id
    )
    stored = await github_service.sync(session, MockGithubAdapter(), story=story)
    meta = next(a for a in stored if a.kind == ArtifactKind.METADATA)
    comps = meta.parsed["components"]
    assert any("HouseholdRollupService" in c for c in comps)
