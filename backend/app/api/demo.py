from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..schemas import SyncResultOut
from ..services.jira import sync_service
from ..services.jira.factory import get_adapter
from .deps import get_session

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/seed", response_model=SyncResultOut)
async def seed_demo_data(session: AsyncSession = Depends(get_session)):
    """Pull the seeded mock-Jira sprint so the app is fully explorable
    without credentials. Demo mode only."""
    if not get_settings().demo_mode:
        raise HTTPException(status_code=409, detail="demo seeding requires DEMO_MODE=true")
    adapter = await get_adapter(session)
    result = await sync_service.sync_from_jira(session, adapter, actor="demo-seed")
    await session.commit()
    return result.as_dict()
