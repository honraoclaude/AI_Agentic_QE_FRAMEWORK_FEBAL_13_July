from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import new_id, utcnow
from .enums import PushStatus, PushType


class PushQueueItem(Base):
    """A pending/completed push to Jira. All pushes are human-approved:
    DRAFT (preview rendered) -> APPROVED -> SENT, or FAILED -> RETRYING.
    Approved pushes are never lost. Fleshed out in Step 2.
    """

    __tablename__ = "push_queue_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    push_type: Mapped[PushType] = mapped_column(
        SAEnum(PushType, native_enum=False, length=16)
    )
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # includes rendered preview
    status: Mapped[PushStatus] = mapped_column(
        SAEnum(PushStatus, native_enum=False, length=16), default=PushStatus.DRAFT
    )
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
