"""Artifact ingestion service: parse + store + audit, list, delete, and
gather the artifacts each agent should consume when it runs.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import AGENT_ARTIFACT_KINDS, Artifact, ArtifactKind, Story
from .. import audit
from ..workflow import NotFoundError
from . import parsers


async def store_artifact(
    session: AsyncSession,
    story: Story,
    *,
    kind: ArtifactKind,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    parsed: dict,
    summary: str,
    parse_error: str | None,
    raw_excerpt: str | None,
    uploaded_by: str,
    source: str = "MANUAL",
    source_ref: str | None = None,
    event_type: str = "ARTIFACT_UPLOADED",
) -> Artifact:
    """Persist a (already-parsed) artifact + audit event. Shared by the manual
    upload path and the Copado ingest path so both behave identically once the
    payload has been normalised into a `parsed` shape."""
    artifact = Artifact(
        story_id=story.id,
        kind=kind,
        filename=filename[:256],
        content_type=content_type,
        size_bytes=size_bytes,
        parsed=parsed,
        summary=summary,
        parse_error=parse_error,
        raw_excerpt=raw_excerpt,
        uploaded_by=uploaded_by or "unknown",
        source=source,
        source_ref=source_ref,
    )
    session.add(artifact)
    await session.flush()

    await audit.record_event(
        session,
        event_type=event_type,
        entity_type="artifact",
        entity_id=artifact.id,
        actor=uploaded_by or "unknown",
        payload={
            "story_id": story.id,
            "jira_key": story.jira_key,
            "kind": kind.value,
            "filename": artifact.filename,
            "size_bytes": artifact.size_bytes,
            "summary": artifact.summary,
            "parse_error": artifact.parse_error,
            "source": source,
            "source_ref": source_ref,
        },
    )
    return artifact


async def create_artifact(
    session: AsyncSession,
    story_id: str,
    *,
    kind: ArtifactKind | None,
    filename: str,
    content_type: str | None,
    raw_bytes: bytes,
    uploaded_by: str,
) -> Artifact:
    story = await session.get(Story, story_id)
    if story is None:
        raise NotFoundError(f"story {story_id} not found")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_bytes.decode("utf-8", errors="replace")

    if kind is None:  # AUTO-detect
        kind = parsers.detect_kind(filename, text)

    result = parsers.parse(kind, text)
    return await store_artifact(
        session,
        story,
        kind=kind,
        filename=filename,
        content_type=content_type,
        size_bytes=len(raw_bytes),
        parsed=result["parsed"],
        summary=result["summary"],
        parse_error=result["error"],
        raw_excerpt=text[: parsers.RAW_EXCERPT_CAP],
        uploaded_by=uploaded_by,
        source="MANUAL",
    )


async def list_artifacts(session: AsyncSession, story_id: str) -> list[Artifact]:
    return list(
        (
            await session.execute(
                select(Artifact)
                .where(Artifact.story_id == story_id)
                .order_by(Artifact.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def delete_artifact(session: AsyncSession, artifact_id: str, actor: str) -> None:
    artifact = await session.get(Artifact, artifact_id)
    if artifact is None:
        raise NotFoundError(f"artifact {artifact_id} not found")
    payload = {
        "story_id": artifact.story_id,
        "kind": artifact.kind.value,
        "filename": artifact.filename,
    }
    await session.delete(artifact)
    await audit.record_event(
        session,
        event_type="ARTIFACT_DELETED",
        entity_type="artifact",
        entity_id=artifact_id,
        actor=actor or "unknown",
        payload=payload,
    )


async def gather_for_agent(
    session: AsyncSession, story_id: str, agent_key: str
) -> list[dict]:
    """Return the parsed artifacts an agent consumes, newest first per kind.
    Shape per item: {kind, filename, summary, parsed}."""
    kinds = AGENT_ARTIFACT_KINDS.get(agent_key)
    if not kinds:
        return []
    rows = (
        (
            await session.execute(
                select(Artifact)
                .where(
                    Artifact.story_id == story_id,
                    Artifact.kind.in_(kinds),
                )
                .order_by(Artifact.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "kind": a.kind.value,
            "filename": a.filename,
            "summary": a.summary,
            "parsed": a.parsed,
            "source": a.source,
        }
        for a in rows
    ]
