"""GitHub branch connection API.

connect: link a story to owner/repo@branch.
sync:    pull the branch's changed files (-> METADATA), CI results (-> SARIF /
         JUNIT / COVERAGE) and changed source (-> GENERIC), stored as artifacts
         the agents consume. Demo mode uses the offline mock adapter.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..services.github import service as github_service
from ..services.github.factory import get_adapter
from ..services.ws import manager
from .deps import get_session

router = APIRouter(prefix="/github", tags=["github"])


class ConnectRequest(BaseModel):
    repo: str = Field(min_length=1, max_length=140, description="owner/repo")
    branch: str = Field(min_length=1, max_length=255)
    jira_key: str | None = Field(default=None, max_length=32)
    story_id: str | None = Field(default=None, max_length=64)
    actor: str = Field(default="unknown", max_length=128)


class SyncRequest(BaseModel):
    jira_key: str | None = Field(default=None, max_length=32)
    story_id: str | None = Field(default=None, max_length=64)
    actor: str = Field(default="github-sync", max_length=128)


@router.get("/status")
async def github_status(env: Settings = Depends(get_settings)):
    return {
        "ok": env.demo_mode or env.github_configured,
        "demo_mode": env.demo_mode,
        "configured": env.github_configured,
    }


@router.post("/connect")
async def connect(body: ConnectRequest, session: AsyncSession = Depends(get_session)):
    if not body.jira_key and not body.story_id:
        raise HTTPException(status_code=422, detail="jira_key or story_id is required")
    story = await github_service.connect(
        session, repo=body.repo, branch=body.branch,
        jira_key=body.jira_key, story_id=body.story_id, actor=body.actor,
    )
    await session.commit()
    return {"story_id": story.id, "jira_key": story.jira_key,
            "github_repo": story.github_repo, "github_branch": story.github_branch}


@router.post("/sync")
async def sync(
    body: SyncRequest,
    session: AsyncSession = Depends(get_session),
    env: Settings = Depends(get_settings),
):
    if not body.jira_key and not body.story_id:
        raise HTTPException(status_code=422, detail="jira_key or story_id is required")
    story = await github_service._resolve_story(
        session, jira_key=body.jira_key, story_id=body.story_id
    )
    adapter = get_adapter(env)
    stored = await github_service.sync(session, adapter, story=story, actor=body.actor)
    await session.commit()
    for a in stored:
        await manager.broadcast(
            {"type": "artifact.uploaded", "story_id": story.id, "artifact_id": a.id}
        )
    return {
        "story_id": story.id,
        "jira_key": story.jira_key,
        "repo": story.github_repo,
        "branch": story.github_branch,
        "ingested": [{"artifact_id": a.id, "kind": a.kind.value, "summary": a.summary} for a in stored],
    }
