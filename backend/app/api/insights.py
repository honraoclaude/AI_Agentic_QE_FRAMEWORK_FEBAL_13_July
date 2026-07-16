"""Agent-performance / human-feedback insights."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..services import feedback
from .deps import get_session

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/agents")
async def agent_insights(session: AsyncSession = Depends(get_session)):
    """Per-agent human-feedback analytics: accept / reject / re-run rates, a
    derived trust score, verdict distribution, reject reasons and re-run guidance
    — plus the agents attracting the most human pushback."""
    return await feedback.agent_performance(session)
