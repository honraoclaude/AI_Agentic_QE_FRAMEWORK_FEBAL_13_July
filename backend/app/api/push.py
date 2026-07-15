from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PushQueueItem, PushStatus
from ..schemas import DraftPushRequest, PushActionRequest, PushItemOut
from ..services import settings_service
from ..services.jira import push_service
from ..services.jira.factory import get_adapter
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/push", tags=["jira-push"])


async def _broadcast(item: PushQueueItem) -> None:
    await manager.broadcast(
        {
            "type": "push.status_changed",
            "push_id": item.id,
            "story_id": item.story_id,
            "push_type": item.push_type.value,
            "status": item.status.value,
        }
    )


@router.get("", response_model=list[PushItemOut])
async def list_pushes(
    session: AsyncSession = Depends(get_session),
    status: PushStatus | None = None,
    story_id: str | None = None,
):
    stmt = select(PushQueueItem).order_by(PushQueueItem.created_at.desc())
    if status:
        stmt = stmt.where(PushQueueItem.status == status)
    if story_id:
        stmt = stmt.where(PushQueueItem.story_id == story_id)
    return (await session.execute(stmt)).scalars().all()


@router.post("/draft", response_model=PushItemOut)
async def draft_push(body: DraftPushRequest, session: AsyncSession = Depends(get_session)):
    """Create a DRAFT push with a rendered preview of exactly what will be
    posted. Nothing is sent until a human approves it."""
    cfg = await settings_service.get_all(session)
    platform_url = cfg.get("platform", {}).get("base_url", "http://localhost:5173")
    if body.kind == "agent_summary":
        item = await push_service.draft_agent_summary(
            session, body.run_id, body.actor, platform_url
        )
    else:
        item = await push_service.draft_bdd_scenarios(
            session, body.run_id, body.actor, platform_url
        )
    await session.commit()
    return item


@router.post("/{item_id}/approve", response_model=PushItemOut)
async def approve_push(
    item_id: str, body: PushActionRequest, session: AsyncSession = Depends(get_session)
):
    adapter = await get_adapter(session)
    item = await push_service.approve_and_send(session, adapter, item_id, body.actor)
    await session.commit()
    await _broadcast(item)
    return item


@router.post("/{item_id}/retry", response_model=PushItemOut)
async def retry_push(
    item_id: str, body: PushActionRequest, session: AsyncSession = Depends(get_session)
):
    adapter = await get_adapter(session)
    item = await push_service.retry(session, adapter, item_id, body.actor)
    await session.commit()
    await _broadcast(item)
    return item
