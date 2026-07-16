from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..util import new_id, utcnow
from .enums import ArtifactKind


class Artifact(Base):
    """A CI/CD artifact uploaded against a story (SARIF scan, test results,
    coverage, financial validation, changed-metadata manifest). The engine
    feeds each agent the parsed summary of the artifacts it consumes.

    `parsed` is the normalized structured summary fed to agents; `raw_excerpt`
    keeps a (capped) copy of the original for reference/audit.
    """

    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id"), index=True)
    kind: Mapped[ArtifactKind] = mapped_column(
        SAEnum(ArtifactKind, native_enum=False, length=16)
    )
    filename: Mapped[str] = mapped_column(String(256))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_by: Mapped[str] = mapped_column(String(128), default="unknown")
    # Provenance: MANUAL (uploaded via UI) or COPADO (ingested from a pipeline
    # event). source_ref carries the origin reference, e.g. "US-1234 @ UAT".
    source: Mapped[str] = mapped_column(String(16), default="MANUAL")
    source_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
