"""Pull-sync from Jira (manual sync, single-story refresh).

Every pull writes audit events with field-level diffs. Conflict handling:
if content fields change after agents already ran, the story is flagged
(changed_since_agent_run) — approval history is never overwritten. Stories
that disappear from the sprint are marked OUT_OF_SCOPE, never deleted.
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import AgentRun, Cloud, FcaImpact, ScopeStatus, Story
from ...util import utcnow
from .. import audit, workflow
from .adapter import JiraAdapter, JiraStoryData

# Fields owned by Jira, overwritten on every pull.
_SYNCED_FIELDS = [
    "summary",
    "description",
    "acceptance_criteria",
    "story_points",
    "sprint",
    "jira_status",
    "assignee",
    "labels",
    "priority",
]
# Content fields — a change here after agents ran flags the story.
_CONTENT_FIELDS = {"summary", "description", "acceptance_criteria"}


@dataclass
class SyncResult:
    total: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    out_of_scope: int = 0
    flagged_conflicts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "out_of_scope": self.out_of_scope,
            "flagged_conflicts": self.flagged_conflicts,
        }


def _incoming_values(data: JiraStoryData) -> dict:
    return {
        "summary": data.summary,
        "description": data.description,
        "acceptance_criteria": data.acceptance_criteria,
        "story_points": data.story_points,
        "sprint": data.sprint,
        "jira_status": data.status,
        "assignee": data.assignee,
        "labels": data.labels,
        "priority": data.priority,
    }


async def _story_has_runs(session: AsyncSession, story_id: str) -> bool:
    row = await session.execute(
        select(AgentRun.id).where(AgentRun.story_id == story_id).limit(1)
    )
    return row.scalar_one_or_none() is not None


async def _apply_story(
    session: AsyncSession, data: JiraStoryData, actor: str, result: SyncResult
) -> Story:
    story = (
        await session.execute(select(Story).where(Story.jira_key == data.key))
    ).scalar_one_or_none()
    incoming = _incoming_values(data)

    if story is None:
        story = Story(jira_key=data.key, **incoming)
        if data.fca_impact:
            story.fca_impact = FcaImpact(data.fca_impact)
            story.fca_impact_confirmed = True  # value came from Jira, not an agent
        if data.cloud:
            story.cloud = Cloud(data.cloud)
        story.jira_updated_at = data.updated_at
        story.last_synced_at = utcnow()
        session.add(story)
        await session.flush()
        await audit.record_event(
            session,
            event_type="STORY_SYNCED",
            entity_type="story",
            entity_id=story.id,
            actor=actor,
            payload={"jira_key": data.key, "action": "created", "fields": incoming},
        )
        await workflow.ensure_story_workflow(session, story, actor)
        result.created += 1
        return story

    # Existing story: compute a field-level diff.
    diff = {}
    for f in _SYNCED_FIELDS:
        old = getattr(story, f)
        new = incoming[f]
        if old != new:
            diff[f] = {"old": old, "new": new}
            setattr(story, f, new)

    # FCA impact / cloud from Jira win only when Jira actually has values.
    if data.fca_impact and (
        story.fca_impact is None or story.fca_impact.value != data.fca_impact
    ):
        diff["fca_impact"] = {
            "old": story.fca_impact.value if story.fca_impact else None,
            "new": data.fca_impact,
        }
        story.fca_impact = FcaImpact(data.fca_impact)
        story.fca_impact_confirmed = True
    if data.cloud and (story.cloud is None or story.cloud.value != data.cloud):
        diff["cloud"] = {
            "old": story.cloud.value if story.cloud else None,
            "new": data.cloud,
        }
        story.cloud = Cloud(data.cloud)

    if story.scope_status == ScopeStatus.OUT_OF_SCOPE:
        diff["scope_status"] = {"old": "OUT_OF_SCOPE", "new": "ACTIVE"}
        story.scope_status = ScopeStatus.ACTIVE

    story.jira_updated_at = data.updated_at
    story.last_synced_at = utcnow()

    if not diff:
        result.unchanged += 1
        return story

    content_changed = bool(_CONTENT_FIELDS & set(diff))
    if content_changed and await _story_has_runs(session, story.id):
        story.changed_since_agent_run = True
        result.flagged_conflicts.append(story.jira_key)

    await audit.record_event(
        session,
        event_type="STORY_SYNCED",
        entity_type="story",
        entity_id=story.id,
        actor=actor,
        payload={
            "jira_key": story.jira_key,
            "action": "updated",
            "diff": diff,
            "flagged_changed_since_agent_run": story.changed_since_agent_run,
        },
    )
    result.updated += 1
    return story


async def sync_from_jira(
    session: AsyncSession,
    adapter: JiraAdapter,
    actor: str = "system",
    jql: str | None = None,
) -> SyncResult:
    result = SyncResult()
    await audit.record_event(
        session,
        event_type="SYNC_STARTED",
        entity_type="sync",
        entity_id="jira",
        actor=actor,
        payload={"jql": jql},
    )

    incoming = await adapter.fetch_stories(jql)
    result.total = len(incoming)
    seen_keys = {d.key for d in incoming}
    for data in incoming:
        await _apply_story(session, data, actor, result)

    # Stories no longer in the sprint: OUT_OF_SCOPE, never deleted.
    active = (
        (
            await session.execute(
                select(Story).where(Story.scope_status == ScopeStatus.ACTIVE)
            )
        )
        .scalars()
        .all()
    )
    for story in active:
        if story.jira_key not in seen_keys:
            story.scope_status = ScopeStatus.OUT_OF_SCOPE
            result.out_of_scope += 1
            await audit.record_event(
                session,
                event_type="STORY_OUT_OF_SCOPE",
                entity_type="story",
                entity_id=story.id,
                actor=actor,
                payload={"jira_key": story.jira_key},
            )

    await audit.record_event(
        session,
        event_type="SYNC_COMPLETED",
        entity_type="sync",
        entity_id="jira",
        actor=actor,
        payload=result.as_dict(),
    )
    return result


async def refresh_story(
    session: AsyncSession, adapter: JiraAdapter, jira_key: str, actor: str = "system"
) -> Story | None:
    """Single-story refresh (the per-card refresh icon)."""
    data = await adapter.fetch_story(jira_key)
    if data is None:
        return None
    result = SyncResult()
    story = await _apply_story(session, data, actor, result)
    return story
