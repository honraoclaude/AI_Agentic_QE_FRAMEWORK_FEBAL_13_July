"""Copado CI/CD ingest API (Phase 1).

Copado Functions POST pipeline results here; each is normalised into an existing
artifact kind and stored against the matching story so the agents consume it.
Authenticated with a shared secret (skipped in demo mode). A demo-only
/simulate endpoint injects sample results so the flow runs without a real org.
"""

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..services.copado import fixtures
from ..services.copado import service as copado_service
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/copado", tags=["copado"])


class CopadoResultIn(BaseModel):
    result_type: str = Field(min_length=1, max_length=32)
    payload: Any
    jira_key: str | None = Field(default=None, max_length=32)
    copado_user_story_id: str | None = Field(default=None, max_length=64)
    run: dict | None = None
    actor: str = Field(default="copado", max_length=128)


class SimulateRequest(BaseModel):
    jira_key: str = Field(min_length=1, max_length=32)
    environment: str = Field(default="UAT", max_length=32)


def _authenticate(env: Settings, signature: str | None) -> None:
    """Shared-secret check. Demo mode is open; otherwise the secret must match."""
    if env.demo_mode:
        return
    secret = env.copado_webhook_secret
    if not secret:
        raise HTTPException(status_code=503, detail="Copado webhook secret not configured")
    if not signature or not hmac.compare_digest(signature, secret):
        raise HTTPException(status_code=401, detail="invalid Copado signature")


async def _broadcast(story_id: str, artifact_id: str) -> None:
    await manager.broadcast(
        {"type": "artifact.uploaded", "story_id": story_id, "artifact_id": artifact_id}
    )


@router.get("/status")
async def copado_status(env: Settings = Depends(get_settings)):
    return {
        "ok": env.demo_mode or env.copado_configured,
        "demo_mode": env.demo_mode,
        "configured": env.copado_configured,
    }


@router.post("/results")
async def ingest_result(
    body: CopadoResultIn,
    x_copado_signature: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_settings),
):
    _authenticate(env, x_copado_signature)
    if not body.jira_key and not body.copado_user_story_id:
        raise HTTPException(
            status_code=422, detail="one of jira_key or copado_user_story_id is required"
        )
    story, artifact = await copado_service.ingest_result(
        session,
        result_type=body.result_type,
        payload=body.payload,
        jira_key=body.jira_key,
        copado_user_story_id=body.copado_user_story_id,
        run=body.run,
        actor=body.actor,
    )
    await session.commit()
    await _broadcast(story.id, artifact.id)
    return {
        "story_id": story.id,
        "jira_key": story.jira_key,
        "copado_user_story_id": story.copado_user_story_id,
        "artifact_id": artifact.id,
        "kind": artifact.kind.value,
        "summary": artifact.summary,
        "source_ref": artifact.source_ref,
    }


@router.post("/simulate")
async def simulate(
    body: SimulateRequest,
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_settings),
):
    """Demo-only: inject a sample Copado pipeline run against a story."""
    if not env.demo_mode:
        raise HTTPException(status_code=409, detail="simulate requires DEMO_MODE=true")
    us_id = f"US-DEMO-{body.jira_key}"
    created = []
    for result in fixtures.sample_results(body.environment):
        story, artifact = await copado_service.ingest_result(
            session,
            result_type=result["result_type"],
            payload=result["payload"],
            jira_key=body.jira_key,
            copado_user_story_id=us_id,
            run=result.get("run"),
            actor="copado-sim",
        )
        created.append(
            {"artifact_id": artifact.id, "kind": artifact.kind.value, "summary": artifact.summary}
        )
    await session.commit()
    for c in created:
        await _broadcast(story.id, c["artifact_id"])
    return {"jira_key": body.jira_key, "copado_user_story_id": us_id, "ingested": created}
