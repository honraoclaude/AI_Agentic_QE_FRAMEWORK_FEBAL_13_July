from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..util import new_id, utcnow
from .enums import GateStatus, Phase


class Gate(Base):
    """End-of-phase checkpoint. One gate per story per phase."""

    __tablename__ = "gates"
    __table_args__ = (UniqueConstraint("story_id", "phase", name="uq_gate_phase"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    phase: Mapped[Phase] = mapped_column(SAEnum(Phase, native_enum=False, length=16))
    status: Mapped[GateStatus] = mapped_column(
        SAEnum(GateStatus, native_enum=False, length=24), default=GateStatus.LOCKED
    )

    approver_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approver_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Snapshot at sign-off time: accepted run ids + output hashes (evidence pack).
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    story = relationship("Story", back_populates="gates")
