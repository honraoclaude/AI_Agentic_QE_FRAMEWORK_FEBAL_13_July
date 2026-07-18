from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun
from ..schemas import AcceptRequest, ApproveRequest, RejectRequest, RerunRequest, RunOut
from ..services import replay as replay_service
from ..services import workflow
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/runs", tags=["agent-runs"])


async def _broadcast_run(run: AgentRun) -> None:
    await manager.broadcast(
        {
            "type": "run.status_changed",
            "run_id": run.id,
            "story_id": run.story_id,
            "agent_key": run.agent_key,
            "status": run.status.value,
        }
    )


@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, session: AsyncSession = Depends(get_session)):
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise workflow.NotFoundError("agent run not found")
    return run


@router.post("/{run_id}/approve", response_model=RunOut)
async def approve_and_run(
    run_id: str, body: ApproveRequest, session: AsyncSession = Depends(get_session)
):
    run = await workflow.approve_and_run(session, run_id, body.approver)
    await session.commit()
    await _broadcast_run(run)
    return run


@router.post("/{run_id}/accept", response_model=RunOut)
async def accept_run(
    run_id: str, body: AcceptRequest, session: AsyncSession = Depends(get_session)
):
    run = await workflow.accept_run(session, run_id, body.actor, body.reason)
    await session.commit()
    await _broadcast_run(run)
    return run


@router.post("/{run_id}/reject", response_model=RunOut)
async def reject_run(
    run_id: str, body: RejectRequest, session: AsyncSession = Depends(get_session)
):
    run = await workflow.reject_run(session, run_id, body.actor, body.reason)
    await session.commit()
    await _broadcast_run(run)
    return run


@router.post("/{run_id}/replay")
async def replay_run(run_id: str, session: AsyncSession = Depends(get_session)):
    """Reproducibility check: re-execute with freshly gathered inputs and
    compare hashes. Persists nothing to the run; audited as RUN_REPLAYED."""
    report = await replay_service.replay_run(session, run_id, actor="auditor")
    await session.commit()  # the audit event
    return report


@router.post("/{run_id}/rerun", response_model=RunOut)
async def request_rerun(
    run_id: str, body: RerunRequest, session: AsyncSession = Depends(get_session)
):
    child = await workflow.request_rerun(session, run_id, body.actor, body.guidance)
    await session.commit()
    await _broadcast_run(child)
    return child
