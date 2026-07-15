from sqlalchemy import select

from app.models import AuditEvent, FcaImpact, ScopeStatus, Story
from app.services import workflow
from app.services.jira import sync_service


async def test_initial_sync_creates_stories_with_workflow(session, adapter):
    result = await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()

    assert result.total == 8
    assert result.created == 8
    assert result.out_of_scope == 0

    stories = list((await session.execute(select(Story))).scalars())
    assert len(stories) == 8

    # Jira-supplied custom fields land correctly.
    s101 = next(s for s in stories if s.jira_key == "WLTH-101")
    assert s101.fca_impact == FcaImpact.HIGH
    assert s101.fca_impact_confirmed is True

    # Missing custom fields stay None (agent will propose, human confirms).
    s108 = next(s for s in stories if s.jira_key == "WLTH-108")
    assert s108.fca_impact is None
    assert s108.fca_impact_confirmed is False


async def test_resync_is_idempotent(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    result = await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    assert result.created == 0
    assert result.updated == 0
    assert result.unchanged == 8


async def test_update_produces_field_diff_in_audit(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()

    adapter.simulate_update("WLTH-103", summary="Convert referred prospects (revised)")
    result = await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    assert result.updated == 1

    events = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "STORY_SYNCED")
            )
        ).scalars()
    )
    diffs = [e for e in events if e.payload.get("action") == "updated"]
    assert len(diffs) == 1
    assert "summary" in diffs[0].payload["diff"]
    assert diffs[0].payload["diff"]["summary"]["new"].endswith("(revised)")


async def test_jira_change_after_agent_run_flags_conflict(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()

    # An agent runs...
    run = await workflow.latest_run(session, story.id, "story_quality")
    await workflow.approve_and_run(session, run.id, approver="Test Lead")
    await session.commit()

    # ...then someone edits the AC in Jira.
    adapter.simulate_update(
        "WLTH-101",
        acceptance_criteria=["Rollup sums all accounts", "NEW: include ISAs"],
    )
    result = await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()

    assert "WLTH-101" in result.flagged_conflicts
    await session.refresh(story)
    assert story.changed_since_agent_run is True
    # Approval history untouched: run record still there, still COMPLETED.
    await session.refresh(run)
    assert run.approved_by == "Test Lead"


async def test_removed_story_marked_out_of_scope_never_deleted(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()

    adapter.remove_from_sprint("WLTH-106")
    result = await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()

    assert result.out_of_scope == 1
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-106"))
    ).scalar_one()  # still exists
    assert story.scope_status == ScopeStatus.OUT_OF_SCOPE
