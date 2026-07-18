from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import new_id, utcnow


class FlakySignature(Base):
    """Cross-run memory of a recurring test failure — Flaky-Test Intelligence.

    A signature is a normalised fingerprint of (test name + failure message)
    with volatile parts (numbers, ids, durations) stripped, so the same
    underlying failure matches across runs and stories. The ledger scores
    flakiness and supports an owned, EXPIRING quarantine — quarantine that
    never expires is how test suites rot.
    """

    __tablename__ = "flaky_signatures"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    signature: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    test_name: Mapped[str] = mapped_column(String(256))
    normalized_message: Mapped[str] = mapped_column(Text, default="")

    occurrences: Mapped[int] = mapped_column(Integer, default=0)
    flaky_votes: Mapped[int] = mapped_column(Integer, default=0)  # analyst said FLAKY
    runs_seen: Mapped[list] = mapped_column(JSON, default=list)   # run ids (dedupe)
    stories_seen: Mapped[list] = mapped_column(JSON, default=list)  # jira keys
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    flake_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100

    status: Mapped[str] = mapped_column(String(12), default="WATCH")  # WATCH|QUARANTINED|CLEARED
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quarantine_expiry: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
