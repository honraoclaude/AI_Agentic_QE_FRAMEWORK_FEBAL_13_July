from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import SyncRequest, SyncResultOut
from ..services.jira import sync_service
from ..services.jira.factory import get_adapter
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/jira", tags=["jira"])


@router.post("/sync", response_model=SyncResultOut)
async def sync_from_jira(
    body: SyncRequest, session: AsyncSession = Depends(get_session)
):
    """Manual 'Sync from Jira'. Pulls stories matching the configured JQL
    (or the override in the request body) and returns counts for the toast."""
    adapter = await get_adapter(session)
    result = await sync_service.sync_from_jira(
        session, adapter, actor=body.actor or "system", jql=body.jql
    )
    await session.commit()
    await manager.broadcast({"type": "sync.completed", **result.as_dict()})
    return result.as_dict()


@router.post("/test-connection")
async def test_connection(session: AsyncSession = Depends(get_session)):
    adapter = await get_adapter(session)
    return await adapter.test_connection()
