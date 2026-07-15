from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class AuditEvent(Base):
    """Append-only, hash-chained audit trail (design target: 7-year retention).

    Each event's event_hash covers the previous event's hash, so any
    tampering with a historical row breaks the chain and is detectable.
    Enforced append-only via: no update/delete endpoints, no ORM mutation
    paths, and DB triggers (see database.py).

    created_at is stored as an ISO-8601 string because it is an input to the
    hash — the stored bytes and the hashed bytes must be identical. ISO
    strings sort correctly for range filters.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(128), default="system")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
