"""Agent-performance / human-feedback insights."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException
from pydantic import BaseModel, Field

from ..services import agent_health, evals, feedback, flaky_intel
from .deps import get_session

router = APIRouter(prefix="/insights", tags=["insights"])


class QuarantineRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    owner: str = Field(min_length=1, max_length=128)
    expiry_days: int = Field(ge=1, le=90)
    note: str = Field(default="", max_length=2000)


class ClearRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=2000)


@router.get("/agents")
async def agent_insights(session: AsyncSession = Depends(get_session)):
    """Per-agent human-feedback analytics: accept / reject / re-run rates, a
    derived trust score, verdict distribution, reject reasons and re-run guidance
    — plus the agents attracting the most human pushback."""
    return await feedback.agent_performance(session)


@router.get("/agent-health")
async def operational_health(session: AsyncSession = Depends(get_session)):
    """Operational (SRE) health of the agent fleet: failure rates, latency,
    token spend, per-prompt-version reliability, and threshold alerts.
    Deterministic aggregation — no model calls."""
    return await agent_health.compute(session)


@router.get("/eval-scorecard")
async def eval_scorecard():
    """The golden-dataset eval harness, live: every agent with a golden file,
    graded now against the demo path — pass/fail counts and any failing
    checks. No DB — pure computation over backend/evals/golden/*.json."""
    return evals.scorecard()


@router.get("/flaky-tests")
async def flaky_ledger(session: AsyncSession = Depends(get_session)):
    """Flaky-Test Intelligence: cross-run failure signatures with flake
    scores, and the owned/expiring quarantine list."""
    return await flaky_intel.ledger(session)


@router.post("/flaky-tests/{sig_id}/quarantine")
async def quarantine_signature(
    sig_id: str, body: QuarantineRequest, session: AsyncSession = Depends(get_session)
):
    """Quarantine a flaky signature — owner + expiry (1-90 days) mandatory."""
    try:
        result = await flaky_intel.quarantine(
            session, sig_id, body.actor, body.owner, body.expiry_days, body.note
        )
    except flaky_intel.FlakyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return result


@router.post("/flaky-tests/{sig_id}/clear")
async def clear_signature(
    sig_id: str, body: ClearRequest, session: AsyncSession = Depends(get_session)
):
    """Stop tracking: the flakiness is fixed or the signature was wrong."""
    try:
        result = await flaky_intel.clear(session, sig_id, body.actor, body.note)
    except flaky_intel.FlakyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return result
