"""Replay Verifier: the audit guarantee, demonstrated — a recorded run either
reproduces byte-for-byte, names exactly which inputs drifted, or exposes a
divergent/tampered output."""

import pytest
from sqlalchemy import select

from app.models import Story
from app.services import replay, workflow
from app.services.jira import sync_service


async def _completed_run(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()
    run = await workflow.latest_run(session, story.id, "story_quality")
    run = await workflow.approve_and_run(session, run.id, approver="Test Lead")
    await session.commit()
    return story, run


async def test_untouched_run_reproduces_exactly(session, adapter):
    story, run = await _completed_run(session, adapter)
    report = await replay.replay_run(session, run.id, actor="auditor")
    assert report["status"] == "REPRODUCED"
    assert report["input_match"] and report["output_match"]
    assert report["deterministic"] is True
    assert report["verdict_stable"] is True


async def test_story_edit_is_reported_as_input_drift(session, adapter):
    story, run = await _completed_run(session, adapter)
    story.summary = story.summary + " (scope changed after the run)"
    await session.flush()
    report = await replay.replay_run(session, run.id, actor="auditor")
    assert report["status"] == "INPUT_DRIFT"
    assert "story" in report["drift"]


async def test_tampered_output_hash_is_exposed(session, adapter):
    story, run = await _completed_run(session, adapter)
    run.output_hash = "0" * 64  # simulate tampering with the stored record
    await session.flush()
    report = await replay.replay_run(session, run.id, actor="auditor")
    assert report["status"] == "OUTPUT_DIVERGED"
    assert report["input_match"] and not report["output_match"]


async def test_unexecuted_run_cannot_be_replayed(session, adapter):
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    story = (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()
    run = await workflow.latest_run(session, story.id, "story_quality")  # PROPOSED
    with pytest.raises(replay.ReplayError):
        await replay.replay_run(session, run.id, actor="auditor")
