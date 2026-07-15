from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import work_service
from .deps import get_session

router = APIRouter(prefix="/work", tags=["work-queue"])


@router.get("/roles")
async def list_roles():
    """The canonical role list — single source of truth for the UI selector."""
    return {"roles": work_service.ROLES}


@router.get("")
async def get_work(
    role: str = Query(..., description="One of the canonical roles"),
    session: AsyncSession = Depends(get_session),
):
    """Pending work items relevant to `role` (gate sign-offs for the role,
    plus operator actions for the QE Lead)."""
    if not work_service.is_valid_role(role):
        raise HTTPException(
            status_code=422,
            detail=f"unknown role '{role}'; expected one of {work_service.ROLES}",
        )
    return await work_service.get_work(session, role)
