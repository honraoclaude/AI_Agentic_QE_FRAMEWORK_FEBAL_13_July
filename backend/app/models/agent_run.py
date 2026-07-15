from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..util import new_id, utcnow
from .enums import Phase, RunStatus


class AgentRun(Base):
    """One execution of one agent against one story.

    Re-runs create a NEW row (attempt + 1, parent_run_id set) so the full
    lineage is preserved for the diff view and the audit trail.
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("story_id", "agent_key", "attempt", name="uq_run_attempt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    agent_key: Mapped[str] = mapped_column(String(64), index=True)
    phase: Mapped[Phase] = mapped_column(SAEnum(Phase, native_enum=False, length=16))
    sequence: Mapped[int] = mapped_column(Integer)  # order within the phase
    attempt: Mapped[int] = mapped_column(Integer, default=1)

    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, native_enum=False, length=24), default=RunStatus.PROPOSED
    )

    prompt_version: Mapped[str] = mapped_column(String(16), default="v1")
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Re-run-with-guidance: text injected into the agent's next prompt.
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_runs.id"), nullable=True
    )

    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    story = relationship("Story", back_populates="runs")
