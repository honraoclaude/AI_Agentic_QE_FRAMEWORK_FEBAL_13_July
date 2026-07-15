import csv
import io
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent
from ..schemas import AuditEventOut
from ..services.audit import verify_chain
from .deps import get_session

router = APIRouter(prefix="/audit", tags=["audit"])

# Read-only router by design: the audit trail has no create/update/delete
# endpoints. Events are written internally by services only.


def _apply_filters(
    stmt,
    entity_type: str | None,
    entity_id: str | None,
    event_type: str | None,
    actor: str | None,
    since: str | None,
    until: str | None,
):
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    if actor:
        stmt = stmt.where(AuditEvent.actor == actor)
    if since:
        stmt = stmt.where(AuditEvent.created_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.created_at <= until)
    return stmt


@router.get("", response_model=list[AuditEventOut])
async def list_events(
    session: AsyncSession = Depends(get_session),
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    actor: str | None = None,
    since: str | None = Query(None, description="ISO-8601 lower bound"),
    until: str | None = Query(None, description="ISO-8601 upper bound"),
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    stmt = _apply_filters(
        select(AuditEvent), entity_type, entity_id, event_type, actor, since, until
    )
    stmt = stmt.order_by(AuditEvent.id.desc()).limit(limit).offset(offset)
    return (await session.execute(stmt)).scalars().all()


@router.get("/export")
async def export_events(
    session: AsyncSession = Depends(get_session),
    format: str = Query("json", pattern="^(json|csv)$"),
    entity_type: str | None = None,
    entity_id: str | None = None,
    event_type: str | None = None,
    actor: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    """Compliance export (CSV/JSON), oldest first, full chain fields included."""
    stmt = _apply_filters(
        select(AuditEvent), entity_type, entity_id, event_type, actor, since, until
    ).order_by(AuditEvent.id)
    events = (await session.execute(stmt)).scalars().all()

    if format == "json":
        body = json.dumps(
            [AuditEventOut.model_validate(e).model_dump() for e in events],
            indent=2,
            default=str,
        )
        return StreamingResponse(
            iter([body]),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=audit_export.json"},
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "created_at",
            "event_type",
            "entity_type",
            "entity_id",
            "actor",
            "payload",
            "payload_hash",
            "prev_hash",
            "event_hash",
        ]
    )
    for e in events:
        writer.writerow(
            [
                e.id,
                e.created_at,
                e.event_type,
                e.entity_type,
                e.entity_id,
                e.actor,
                json.dumps(e.payload, default=str),
                e.payload_hash,
                e.prev_hash,
                e.event_hash,
            ]
        )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
    )


@router.get("/verify")
async def verify(session: AsyncSession = Depends(get_session)):
    """Re-derive every hash in the chain — tamper detection for compliance review."""
    return await verify_chain(session)
