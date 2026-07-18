from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import new_id, utcnow


class Release(Base):
    """A release train: the grouping leadership actually thinks in.

    Stories are linked by id list (JSON) — deliberately association-light so
    the existing stories table is untouched. The release is the grain for the
    executive MI pack and (later) Copado Phase-2 gating.
    """

    __tablename__ = "releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. "Release 26.8"
    target_date: Mapped[str] = mapped_column(String(10), default="")  # ISO date
    status: Mapped[str] = mapped_column(String(12), default="PLANNED")  # PLANNED|RELEASED
    notes: Mapped[str] = mapped_column(Text, default="")
    story_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReportSnapshot(Base):
    """A SEALED report: the numbers leadership saw, immutable and provable.

    Live views drift as data changes; a snapshot is generated once, persisted
    with a canonical hash, and the hash is recorded in the append-only audit
    chain (REPORT_SEALED) — six months later "the numbers the board saw" are
    reproducible and tamper-evident.
    """

    __tablename__ = "report_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    release_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="EXEC_MI")
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    generated_by: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
