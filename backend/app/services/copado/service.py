"""Copado ingest service (Phase 1).

Resolve the target story, normalise a Copado result payload into an existing
artifact shape, store it (source=COPADO) and audit it. Links the Copado User
Story id to the story on first sighting.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import Story
from ..artifacts import service as artifact_service
from ..workflow import NotFoundError
from . import normaliser


async def _resolve_story(
    session: AsyncSession, *, jira_key: str | None, copado_user_story_id: str | None
) -> Story:
    story: Story | None = None
    if copado_user_story_id:
        story = (
            await session.execute(
                select(Story).where(Story.copado_user_story_id == copado_user_story_id)
            )
        ).scalar_one_or_none()
    if story is None and jira_key:
        story = (
            await session.execute(select(Story).where(Story.jira_key == jira_key))
        ).scalar_one_or_none()
    if story is None:
        raise NotFoundError(
            "no story matches the Copado result "
            f"(jira_key={jira_key!r}, copado_user_story_id={copado_user_story_id!r})"
        )
    # Link on first sighting so future results resolve directly.
    if copado_user_story_id and not story.copado_user_story_id:
        story.copado_user_story_id = copado_user_story_id
    return story


def _source_ref(copado_user_story_id: str | None, run: dict | None) -> str:
    run = run or {}
    us = copado_user_story_id or run.get("user_story") or "Copado"
    env = run.get("environment")
    run_id = run.get("run_id")
    parts = [us]
    if env:
        parts.append(f"@ {env}")
    if run_id:
        parts.append(f"({run_id})")
    return " ".join(parts)[:256]


async def ingest_result(
    session: AsyncSession,
    *,
    result_type: str,
    payload,
    jira_key: str | None = None,
    copado_user_story_id: str | None = None,
    run: dict | None = None,
    actor: str = "copado",
):
    """Normalise + store one Copado result as an artifact on the resolved story."""
    story = await _resolve_story(
        session, jira_key=jira_key, copado_user_story_id=copado_user_story_id
    )
    norm = normaliser.normalise(result_type, payload)
    artifact = await artifact_service.store_artifact(
        session,
        story,
        kind=norm["kind"],
        filename=norm["filename"],
        content_type="application/json",
        size_bytes=0,
        parsed=norm["parsed"],
        summary=norm["summary"],
        parse_error=norm["parse_error"],
        raw_excerpt=None,
        uploaded_by=actor,
        source="COPADO",
        source_ref=_source_ref(copado_user_story_id, run),
        event_type="ARTIFACT_INGESTED",
    )
    return story, artifact
