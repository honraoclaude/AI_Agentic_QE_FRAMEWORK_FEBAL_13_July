"""Risk Acceptance Register — the quality-debt ledger endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import risk_register
from .deps import get_session

router = APIRouter(prefix="/risk-register", tags=["risk-register"])


class RegisterAction(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=4000)


@router.get("")
async def list_register(
    story_id: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    """The register: every knowingly-accepted risk (run accepted despite
    findings, gate signed over WARNs, CONDITIONAL_GO), each with owner,
    rationale, severity-derived review-by date and OPEN/REVIEWED/CLOSED
    status. Sweeps (idempotently) before returning, so it is always current."""
    result = await risk_register.list_register(session, story_id, status)
    await session.commit()  # any newly swept entries + their audit events
    return result


@router.post("/{entry_id}/review")
async def review_entry(
    entry_id: str, body: RegisterAction, session: AsyncSession = Depends(get_session)
):
    """Re-affirm: still a known, tolerated risk. Restarts the review window."""
    try:
        result = await risk_register.review(session, entry_id, body.actor, body.note)
    except risk_register.RegisterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return result


@router.post("/{entry_id}/close")
async def close_entry(
    entry_id: str, body: RegisterAction, session: AsyncSession = Depends(get_session)
):
    """The risk no longer exists (fixed, descoped, superseded)."""
    try:
        result = await risk_register.close(session, entry_id, body.actor, body.note)
    except risk_register.RegisterError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return result
