"""Stakeholder reporting: releases, sealed MI packs, and the live cuts."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Release, ReportSnapshot, Story
from ..services import reporting
from .deps import get_session

router = APIRouter(prefix="/reports", tags=["reports"])


class ReleaseCreate(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=64)
    target_date: str = Field(default="", max_length=10)
    story_ids: list[str] = Field(default_factory=list)


class ReleaseStories(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    story_ids: list[str]


class SealRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)


@router.get("/releases")
async def list_releases(session: AsyncSession = Depends(get_session)):
    releases = (
        await session.execute(select(Release).order_by(Release.created_at.desc()))
    ).scalars().all()
    snaps = (
        await session.execute(select(ReportSnapshot))
    ).scalars().all()
    by_release: dict[str, list] = {}
    for s in snaps:
        by_release.setdefault(s.release_id, []).append({
            "id": s.id, "kind": s.kind, "payload_hash": s.payload_hash,
            "generated_by": s.generated_by,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return [
        {
            "id": r.id, "name": r.name, "target_date": r.target_date,
            "status": r.status, "story_ids": r.story_ids or [],
            "snapshots": sorted(
                by_release.get(r.id, []), key=lambda x: x["created_at"] or "", reverse=True
            ),
        }
        for r in releases
    ]


@router.post("/releases")
async def create_release(
    body: ReleaseCreate, session: AsyncSession = Depends(get_session)
):
    exists = (
        await session.execute(select(Release).where(Release.name == body.name))
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="a release with that name exists")
    for sid in body.story_ids:
        if await session.get(Story, sid) is None:
            raise HTTPException(status_code=400, detail=f"unknown story id {sid}")
    release = Release(
        name=body.name.strip(), target_date=body.target_date,
        story_ids=body.story_ids,
    )
    session.add(release)
    await session.commit()
    return {"id": release.id, "name": release.name}


@router.post("/releases/{release_id}/stories")
async def set_release_stories(
    release_id: str, body: ReleaseStories, session: AsyncSession = Depends(get_session)
):
    release = await session.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="release not found")
    for sid in body.story_ids:
        if await session.get(Story, sid) is None:
            raise HTTPException(status_code=400, detail=f"unknown story id {sid}")
    release.story_ids = body.story_ids
    await session.commit()
    return {"id": release.id, "story_ids": release.story_ids}


@router.get("/releases/{release_id}/mi-preview")
async def mi_preview(release_id: str, session: AsyncSession = Depends(get_session)):
    """Live, UNSEALED preview of the exec MI pack — numbers may still move."""
    release = await session.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="release not found")
    return await reporting.exec_mi_pack(session, release)


@router.post("/releases/{release_id}/seal-mi")
async def seal_mi(
    release_id: str, body: SealRequest, session: AsyncSession = Depends(get_session)
):
    """Seal the MI pack: persist, hash, and record in the audit chain."""
    release = await session.get(Release, release_id)
    if release is None:
        raise HTTPException(status_code=404, detail="release not found")
    meta = await reporting.seal_mi_pack(session, release, body.actor)
    await session.commit()
    return meta


@router.get("/mi/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str, format: str = "html",
    session: AsyncSession = Depends(get_session),
):
    snap = await session.get(ReportSnapshot, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="snapshot not found")
    if format == "json":
        return {"payload": snap.payload, "payload_hash": snap.payload_hash}
    return HTMLResponse(
        content=reporting.render_mi_html(snap.payload, snap.payload_hash)
    )


@router.get("/flow")
async def flow(session: AsyncSession = Depends(get_session)):
    """PM/PO: gate cycle times, HITL queue depth/latency, blocking questions."""
    return await reporting.flow_report(session)


@router.get("/quality")
async def quality(session: AsyncSession = Depends(get_session)):
    """BA/QA: traceability integrity, pyramid, first-time-right, flake index."""
    return await reporting.quality_report(session)


@router.get("/worklist/{story_id}")
async def story_worklist(story_id: str, session: AsyncSession = Depends(get_session)):
    """Dev: this story's findings, strongest first."""
    if await session.get(Story, story_id) is None:
        raise HTTPException(status_code=404, detail="story not found")
    return await reporting.worklist(session, story_id)
