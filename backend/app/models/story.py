from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..util import new_id, utcnow
from .enums import Cloud, FcaImpact, Phase, ScopeStatus


class Story(Base):
    __tablename__ = "stories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    jira_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    # Linked Copado User Story (set on first Copado result sighting for the key).
    copado_user_story_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    summary: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    story_points: Mapped[float | None] = mapped_column(Float, nullable=True)
    sprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    jira_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assignee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # FCA impact may be synced from Jira, or proposed by the Story Quality Agent
    # and confirmed by a human (fca_impact_confirmed tracks which).
    fca_impact: Mapped[FcaImpact | None] = mapped_column(
        SAEnum(FcaImpact, native_enum=False, length=16), nullable=True
    )
    fca_impact_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    cloud: Mapped[Cloud | None] = mapped_column(
        SAEnum(Cloud, native_enum=False, length=16), nullable=True
    )

    current_phase: Mapped[Phase] = mapped_column(
        SAEnum(Phase, native_enum=False, length=16), default=Phase.REFINEMENT
    )
    scope_status: Mapped[ScopeStatus] = mapped_column(
        SAEnum(ScopeStatus, native_enum=False, length=16), default=ScopeStatus.ACTIVE
    )
    released: Mapped[bool] = mapped_column(Boolean, default=False)

    jira_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set when Jira content changed after agents already ran — drives the
    # "Jira changed since last agent run" warning badge. Never silently cleared.
    changed_since_agent_run: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    runs = relationship(
        "AgentRun", back_populates="story", order_by="AgentRun.created_at"
    )
    gates = relationship("Gate", back_populates="story", order_by="Gate.created_at")
