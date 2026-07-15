import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Gate, Story
from ..schemas import GateDecisionRequest, GateOut
from ..services import settings_service, workflow
from ..services.jira import push_service
from ..services.jira.factory import get_adapter
from ..services.ws import manager
from .deps import get_session

logger = logging.getLogger("pact.gates")

router = APIRouter(tags=["gates"])


async def _broadcast_gate(gate: Gate) -> None:
    await manager.broadcast(
        {
            "type": "gate.status_changed",
            "gate_id": gate.id,
            "story_id": gate.story_id,
            "phase": gate.phase.value,
            "status": gate.status.value,
        }
    )


@router.get("/stories/{story_id}/gates", response_model=list[GateOut])
async def story_gates(story_id: str, session: AsyncSession = Depends(get_session)):
    gates = (
        (
            await session.execute(
                select(Gate).where(Gate.story_id == story_id).order_by(Gate.created_at)
            )
        )
        .scalars()
        .all()
    )
    return gates


@router.post("/gates/{gate_id}/signoff", response_model=GateOut)
async def signoff_gate(
    gate_id: str,
    body: GateDecisionRequest,
    session: AsyncSession = Depends(get_session),
):
    gate = await workflow.signoff_gate(
        session, gate_id, body.approver_name, body.approver_role, body.rationale
    )
    # Commit the sign-off + its audit events FIRST. This is the
    # compliance-critical record and must not be lost if the (best-effort)
    # Jira auto-posts below fail to even enqueue.
    await session.commit()
    await _broadcast_gate(gate)

    # Auto-post comment/label/transition/evidence per gate settings — the
    # sign-off itself is the recorded human approval for these pushes. Any
    # failure here is isolated: individual send failures land in the retry
    # queue; a setup failure is logged and the sign-off still stands.
    push_items = []
    try:
        story = await session.get(Story, gate.story_id)
        app_settings = await settings_service.get_all(session)
        adapter = await get_adapter(session)
        push_items = await push_service.handle_gate_signoff(
            session, adapter, story, gate, app_settings, actor=body.approver_name
        )
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("gate %s: failed to enqueue sign-off pushes", gate.id)

    for item in push_items:
        await manager.broadcast(
            {
                "type": "push.status_changed",
                "push_id": item.id,
                "story_id": item.story_id,
                "push_type": item.push_type.value,
                "status": item.status.value,
            }
        )
    return gate


@router.post("/gates/{gate_id}/reject", response_model=GateOut)
async def reject_gate(
    gate_id: str,
    body: GateDecisionRequest,
    session: AsyncSession = Depends(get_session),
):
    gate = await workflow.reject_gate(
        session, gate_id, body.approver_name, body.approver_role, body.rationale
    )
    await session.commit()
    await _broadcast_gate(gate)
    return gate
