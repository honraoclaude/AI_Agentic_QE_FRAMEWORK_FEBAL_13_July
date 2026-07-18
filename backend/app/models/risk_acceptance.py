from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import new_id, utcnow


class RiskAcceptance(Base):
    """One knowingly-accepted risk — the quality-debt ledger.

    Materialised whenever a human accepts a run despite WARN/severe findings,
    signs a gate over WARN verdicts, or accepts a CONDITIONAL_GO. Sign-offs
    stop being terminal events and become managed positions: each entry
    carries an owner-of-record, a rationale, and a review-by date derived
    from severity. A SYSC-style risk register, auto-populated.
    """

    __tablename__ = "risk_acceptances"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    jira_key: Mapped[str] = mapped_column(String(32), index=True)

    # Dedupe key: one source event never creates two entries.
    source_ref: Mapped[str] = mapped_column(String(128), unique=True)
    source: Mapped[str] = mapped_column(String(40))  # RUN_ACCEPTED_WITH_FINDINGS |
    #                                       GATE_SIGNED_OVER_WARN | CONDITIONAL_GO
    agent_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phase: Mapped[str] = mapped_column(String(16))

    severity: Mapped[str] = mapped_column(String(12))  # canonical scale
    title: Mapped[str] = mapped_column(String(256))
    detail: Mapped[str] = mapped_column(Text, default="")

    accepted_by: Mapped[str] = mapped_column(String(128))
    rationale: Mapped[str] = mapped_column(Text, default="")
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    review_by: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(12), default="OPEN")  # OPEN|REVIEWED|CLOSED
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[str] = mapped_column(Text, default="")
    closed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_note: Mapped[str] = mapped_column(Text, default="")
