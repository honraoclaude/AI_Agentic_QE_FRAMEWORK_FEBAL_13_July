"""Append-only, hash-chained audit trail.

Every state transition, agent input/output hash, approval and Jira sync action
goes through record_event(). Events are written in the same transaction as the
state change they describe.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AuditEvent
from ..util import canonical_json, sha256_hex, utcnow_iso

GENESIS_HASH = "0" * 64


def _compute_event_hash(
    *,
    prev_hash: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor: str,
    payload_hash: str,
    created_at: str,
) -> str:
    material = "|".join(
        [prev_hash, event_type, entity_type, entity_id, actor, payload_hash, created_at]
    )
    return sha256_hex(material)


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor: str = "system",
    payload: dict | None = None,
) -> AuditEvent:
    payload = payload or {}
    payload_hash = sha256_hex(canonical_json(payload))

    last = (
        await session.execute(
            select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    prev_hash = last.event_hash if last else GENESIS_HASH

    created_at = utcnow_iso()
    event = AuditEvent(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        actor=actor,
        payload=payload,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        event_hash=_compute_event_hash(
            prev_hash=prev_hash,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            payload_hash=payload_hash,
            created_at=created_at,
        ),
        created_at=created_at,
    )
    session.add(event)
    await session.flush()
    return event


async def verify_chain(session: AsyncSession) -> dict:
    """Walk the whole chain and re-derive every hash. Returns a verdict dict
    for the compliance export / integrity endpoint."""
    events = (
        (await session.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
    )
    prev_hash = GENESIS_HASH
    for ev in events:
        if ev.prev_hash != prev_hash:
            return {"valid": False, "broken_at": ev.id, "reason": "prev_hash mismatch"}
        if ev.payload_hash != sha256_hex(canonical_json(ev.payload)):
            return {"valid": False, "broken_at": ev.id, "reason": "payload tampered"}
        expected = _compute_event_hash(
            prev_hash=ev.prev_hash,
            event_type=ev.event_type,
            entity_type=ev.entity_type,
            entity_id=ev.entity_id,
            actor=ev.actor,
            payload_hash=ev.payload_hash,
            created_at=ev.created_at,
        )
        if ev.event_hash != expected:
            return {"valid": False, "broken_at": ev.id, "reason": "event_hash mismatch"}
        prev_hash = ev.event_hash
    return {"valid": True, "events": len(events)}
