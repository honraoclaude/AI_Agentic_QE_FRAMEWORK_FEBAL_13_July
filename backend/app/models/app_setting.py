from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import utcnow


class AppSetting(Base):
    """Non-secret runtime settings (field mappings, per-gate toggles, JQL,
    sync interval). Secrets stay in .env. Populated in Step 2 (settings screen).
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
