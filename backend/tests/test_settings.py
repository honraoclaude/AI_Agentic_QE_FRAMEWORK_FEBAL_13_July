import pytest
from sqlalchemy import select

from app.models import AuditEvent
from app.services import settings_service


async def test_defaults_returned_when_nothing_stored(session):
    cfg = await settings_service.get_all(session)
    assert cfg["jira"]["project_key"] == "WLTH"
    assert cfg["sync"] == {"enabled": False, "interval_minutes": 15}
    assert cfg["gates"]["REFINEMENT"]["label"] == "qe-gate-1-passed"
    assert cfg["gates"]["RELEASE"]["attach_evidence"] is True
    assert cfg["field_mappings"]["acceptance_criteria"]["mode"] == "description"


async def test_partial_update_deep_merges_and_audits(session):
    cfg = await settings_service.update_settings(
        session,
        {
            "sync": {"enabled": True},
            "gates": {"REFINEMENT": {"transition_name": "Ready for Dev"}},
        },
        actor="Honra",
    )
    await session.commit()

    # Patched values applied...
    assert cfg["sync"]["enabled"] is True
    assert cfg["gates"]["REFINEMENT"]["transition_name"] == "Ready for Dev"
    # ...siblings preserved by the deep merge.
    assert cfg["sync"]["interval_minutes"] == 15
    assert cfg["gates"]["REFINEMENT"]["label"] == "qe-gate-1-passed"
    assert cfg["gates"]["TESTING"]["transition_name"] is None

    events = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.event_type == "SETTINGS_UPDATED")
            )
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].actor == "Honra"
    assert events[0].payload["before"]["sync"]["enabled"] is False
    assert events[0].payload["after"]["sync"]["enabled"] is True


async def test_unknown_keys_rejected(session):
    with pytest.raises(ValueError):
        await settings_service.update_settings(session, {"hacks": {}}, actor="x")


async def test_env_summary_never_leaks_secrets():
    summary = settings_service.env_summary()
    assert "jira_api_token" not in summary
    assert isinstance(summary["jira_api_token_set"], bool)
    assert isinstance(summary["anthropic_api_key_set"], bool)
