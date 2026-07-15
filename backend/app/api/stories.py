from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import AgentRun, AuditEvent, Gate, Story
from ..schemas import (
    AuditEventOut,
    RunOut,
    RunSummaryOut,
    StoryBoardOut,
    StoryDetailOut,
)
from ..services.jira import sync_service
from ..services.jira.factory import get_adapter
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/stories", tags=["stories"])


def _latest_runs_only(runs: list[AgentRun]) -> list[AgentRun]:
    """Board view shows one dot per agent: the latest attempt."""
    latest: dict[str, AgentRun] = {}
    for run in runs:
        current = latest.get(run.agent_key)
        if current is None or run.attempt > current.attempt:
            latest[run.agent_key] = run
    return sorted(latest.values(), key=lambda r: (r.phase.value, r.sequence))


@router.get("", response_model=list[StoryBoardOut])
async def list_stories(session: AsyncSession = Depends(get_session)):
    stories = (
        (
            await session.execute(
                select(Story)
                .options(selectinload(Story.runs), selectinload(Story.gates))
                .order_by(Story.jira_key)
            )
        )
        .scalars()
        .all()
    )
    out = []
    for story in stories:
        item = StoryBoardOut.model_validate(story)
        item.runs = [
            RunSummaryOut.model_validate(r) for r in _latest_runs_only(story.runs)
        ]
        out.append(item)
    return out


@router.get("/{story_id}", response_model=StoryDetailOut)
async def get_story(story_id: str, session: AsyncSession = Depends(get_session)):
    story = (
        await session.execute(
            select(Story)
            .where(Story.id == story_id)
            .options(selectinload(Story.runs), selectinload(Story.gates))
        )
    ).scalar_one_or_none()
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")
    return story


@router.get("/{story_id}/runs", response_model=list[RunOut])
async def story_runs(story_id: str, session: AsyncSession = Depends(get_session)):
    runs = (
        (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.story_id == story_id)
                .order_by(AgentRun.created_at)
            )
        )
        .scalars()
        .all()
    )
    return runs


@router.get("/{story_id}/timeline", response_model=list[AuditEventOut])
async def story_timeline(story_id: str, session: AsyncSession = Depends(get_session)):
    """Every audit event touching this story, its runs and its gates —
    drives the drawer timeline (agent runs, approvals, sync events)."""
    story = await session.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")
    run_ids = (
        (await session.execute(select(AgentRun.id).where(AgentRun.story_id == story_id)))
        .scalars()
        .all()
    )
    gate_ids = (
        (await session.execute(select(Gate.id).where(Gate.story_id == story_id)))
        .scalars()
        .all()
    )
    entity_ids = [story_id, *run_ids, *gate_ids]
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id.in_(entity_ids))
                .order_by(AuditEvent.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return events


@router.post("/{story_id}/refresh", response_model=StoryDetailOut)
async def refresh_story(
    story_id: str,
    session: AsyncSession = Depends(get_session),
):
    story = await session.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="story not found")
    adapter = await get_adapter(session)
    refreshed = await sync_service.refresh_story(
        session, adapter, story.jira_key, actor="manual-refresh"
    )
    if refreshed is None:
        raise HTTPException(status_code=404, detail="story no longer exists in Jira")
    await session.commit()
    await manager.broadcast({"type": "story.refreshed", "story_id": story_id})
    return await get_story(story_id, session)
