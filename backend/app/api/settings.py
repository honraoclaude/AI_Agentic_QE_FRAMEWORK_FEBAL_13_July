from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import SettingsOut, SettingsUpdateRequest
from ..services import settings_service
from .deps import get_session

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings_view(session: AsyncSession = Depends(get_session)):
    return SettingsOut(
        env=settings_service.env_summary(),
        settings=await settings_service.get_all(session),
    )


@router.put("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdateRequest, session: AsyncSession = Depends(get_session)
):
    try:
        merged = await settings_service.update_settings(session, body.patch, body.actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    return SettingsOut(env=settings_service.env_summary(), settings=merged)
