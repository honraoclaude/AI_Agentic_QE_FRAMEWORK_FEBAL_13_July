from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AGENT_ARTIFACT_KINDS, ArtifactKind
from ..services.artifacts import service as artifact_service
from ..services.ws import manager
from .deps import get_session

router = APIRouter(tags=["artifacts"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB cap per artifact


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    story_id: str
    kind: ArtifactKind
    filename: str
    content_type: str | None
    size_bytes: int
    parsed: dict
    summary: str
    parse_error: str | None
    raw_excerpt: str | None
    uploaded_by: str
    source: str
    source_ref: str | None
    created_at: datetime


@router.get("/artifacts/consumers")
async def artifact_consumers():
    """Which agents consume which artifact kinds — drives the upload UI hints."""
    by_kind: dict[str, list[str]] = {}
    for agent_key, kinds in AGENT_ARTIFACT_KINDS.items():
        for kind in kinds:
            by_kind.setdefault(kind.value, []).append(agent_key)
    return {"by_kind": by_kind}


@router.get("/stories/{story_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(story_id: str, session: AsyncSession = Depends(get_session)):
    return await artifact_service.list_artifacts(session, story_id)


@router.post("/stories/{story_id}/artifacts", response_model=ArtifactOut)
async def upload_artifact(
    story_id: str,
    file: UploadFile = File(...),
    kind: str = Form("AUTO"),
    uploaded_by: str = Form("unknown"),
    session: AsyncSession = Depends(get_session),
):
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=413, detail=f"artifact exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB cap"
        )
    resolved_kind = None if kind.upper() == "AUTO" else ArtifactKind(kind.upper())
    artifact = await artifact_service.create_artifact(
        session,
        story_id,
        kind=resolved_kind,
        filename=file.filename or "upload.txt",
        content_type=file.content_type,
        raw_bytes=raw,
        uploaded_by=uploaded_by,
    )
    await session.commit()
    await manager.broadcast(
        {"type": "artifact.uploaded", "story_id": story_id, "artifact_id": artifact.id}
    )
    return artifact


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    actor: str = "unknown",
    session: AsyncSession = Depends(get_session),
):
    await artifact_service.delete_artifact(session, artifact_id, actor)
    await session.commit()
    return {"ok": True}
