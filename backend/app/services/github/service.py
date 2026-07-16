"""GitHub ingest service.

connect(): link a story to owner/repo@branch.
sync():    pull the branch's PullItems, parse each with the existing artifact
           parsers, and store them as artifacts (source=GITHUB) so the agents
           consume GitHub-sourced evidence exactly like uploads / Copado.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Story
from .. import audit
from ..artifacts import parsers
from ..artifacts import service as artifact_service
from ..workflow import NotFoundError
from .adapter import GithubAdapter


async def _resolve_story(
    session: AsyncSession, *, jira_key: str | None, story_id: str | None
) -> Story:
    story: Story | None = None
    if story_id:
        story = await session.get(Story, story_id)
    if story is None and jira_key:
        story = (
            await session.execute(select(Story).where(Story.jira_key == jira_key))
        ).scalar_one_or_none()
    if story is None:
        raise NotFoundError(
            f"no story matches (jira_key={jira_key!r}, story_id={story_id!r})"
        )
    return story


async def connect(
    session: AsyncSession,
    *,
    repo: str,
    branch: str,
    jira_key: str | None = None,
    story_id: str | None = None,
    actor: str = "unknown",
) -> Story:
    story = await _resolve_story(session, jira_key=jira_key, story_id=story_id)
    story.github_repo = repo
    story.github_branch = branch
    await audit.record_event(
        session,
        event_type="GITHUB_CONNECTED",
        entity_type="story",
        entity_id=story.id,
        actor=actor,
        payload={"jira_key": story.jira_key, "repo": repo, "branch": branch},
    )
    return story


async def sync(
    session: AsyncSession,
    adapter: GithubAdapter,
    *,
    story: Story,
    actor: str = "github-sync",
):
    """Pull + parse + store the branch's artifacts. Returns the stored artifacts."""
    if not story.github_repo or not story.github_branch:
        raise NotFoundError(f"story {story.jira_key} is not connected to a GitHub branch")

    items = await adapter.fetch_branch_artifacts(story.github_repo, story.github_branch)
    stored = []
    for item in items:
        result = parsers.parse(item.kind, item.text)
        artifact = await artifact_service.store_artifact(
            session,
            story,
            kind=item.kind,
            filename=item.filename,
            content_type="text/plain",
            size_bytes=len(item.text.encode("utf-8")),
            parsed=result["parsed"],
            summary=result["summary"],
            parse_error=result["error"],
            raw_excerpt=item.text[: parsers.RAW_EXCERPT_CAP],
            uploaded_by=actor,
            source="GITHUB",
            source_ref=item.ref,
            event_type="ARTIFACT_INGESTED",
        )
        stored.append(artifact)
    return stored
