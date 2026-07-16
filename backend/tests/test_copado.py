import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import config
from app.api import copado as copado_api
from app.models import ArtifactKind, Story
from app.services.artifacts import service as artifact_service
from app.services.copado import fixtures, normaliser
from app.services.copado import service as copado_service
from app.services.jira import sync_service


async def _seed_story(session, adapter) -> Story:
    await sync_service.sync_from_jira(session, adapter, actor="test")
    await session.commit()
    return (
        await session.execute(select(Story).where(Story.jira_key == "WLTH-101"))
    ).scalar_one()


# ------------------------------------------------------------------ normaliser


def test_normalise_codescan_violations_to_sarif():
    payload = {
        "violations": [
            {"rule": "ApexCRUDViolation", "severity": "high",
             "file": "classes/Rollup.cls", "line": 88, "message": "no FLS"},
            {"rule": "AvoidSoqlInLoops", "severity": "medium",
             "file": "classes/Rollup.cls", "line": 142, "message": "soql in loop"},
        ]
    }
    r = normaliser.normalise("codescan", payload)
    assert r["kind"] == ArtifactKind.SARIF and r["parse_error"] is None
    findings = r["parsed"]["findings"]
    assert len(findings) == 2
    assert findings[0]["rule"] == "ApexCRUDViolation"
    assert findings[0]["location"] == "classes/Rollup.cls:88"
    assert r["parsed"]["counts"] == {"error": 1, "warning": 1}


def test_normalise_codescan_sarif_passthrough():
    sarif = {"version": "2.1.0", "runs": [{"results": [
        {"ruleId": "X", "level": "error", "message": {"text": "boom"}}
    ]}]}
    r = normaliser.normalise("codescan", sarif)
    assert r["kind"] == ArtifactKind.SARIF
    assert r["parsed"]["counts"] == {"error": 1}


def test_normalise_apex_tests_to_junit():
    payload = {"tests": [
        {"name": "a", "className": "T", "outcome": "Pass"},
        {"name": "b", "className": "T", "outcome": "Pass"},
        {"name": "c", "className": "T", "outcome": "Fail", "message": "Too many SOQL"},
    ]}
    r = normaliser.normalise("apex_tests", payload)
    assert r["kind"] == ArtifactKind.JUNIT and r["parse_error"] is None
    p = r["parsed"]
    assert (p["total"], p["passed"], p["failed"]) == (3, 2, 1)
    assert p["failures"][0]["name"] == "c" and "SOQL" in p["failures"][0]["message"]
    assert p["all_tests"] == ["a", "b", "c"]


def test_normalise_commit_to_metadata():
    payload = {"components": [
        {"type": "ApexClass", "name": "HouseholdRollupService"},
        {"type": "ApexTrigger", "name": "FinancialAccountTrigger"},
    ]}
    r = normaliser.normalise("commit", payload)
    assert r["kind"] == ArtifactKind.METADATA
    assert "ApexClass: HouseholdRollupService" in r["parsed"]["components"]


def test_normalise_unknown_type_is_generic():
    r = normaliser.normalise("mystery", {"foo": 1})
    assert r["kind"] == ArtifactKind.GENERIC and r["parse_error"] is None


# ------------------------------------------------------------------ ingest service


async def test_ingest_stores_copado_sourced_artifact(session, adapter):
    story = await _seed_story(session, adapter)
    _, artifact = await copado_service.ingest_result(
        session,
        result_type="codescan",
        payload={"violations": [
            {"rule": "R", "severity": "high", "file": "a.cls", "line": 1, "message": "m"}
        ]},
        jira_key="WLTH-101",
        run={"environment": "UAT", "run_id": "CS-1"},
    )
    await session.flush()
    assert artifact.kind == ArtifactKind.SARIF
    assert artifact.source == "COPADO"
    assert "UAT" in artifact.source_ref and "CS-1" in artifact.source_ref

    # Static Analysis agent consumes SARIF -> the Copado artifact is now available.
    consumed = await artifact_service.gather_for_agent(session, story.id, "static_analysis")
    assert any(c["source"] == "COPADO" and c["kind"] == "SARIF" for c in consumed)


async def test_ingest_links_copado_user_story_then_resolves_by_it(session, adapter):
    story = await _seed_story(session, adapter)
    # First result carries both keys -> links the Copado US id onto the story.
    await copado_service.ingest_result(
        session, result_type="commit",
        payload={"components": [{"type": "ApexClass", "name": "Rollup"}]},
        jira_key="WLTH-101", copado_user_story_id="US-777",
    )
    await session.flush()
    refreshed = await session.get(Story, story.id)
    assert refreshed.copado_user_story_id == "US-777"

    # Second result with ONLY the Copado id still resolves to the same story.
    linked_story, artifact = await copado_service.ingest_result(
        session, result_type="apex_tests",
        payload={"tests": [{"name": "t", "outcome": "Pass"}]},
        copado_user_story_id="US-777",
    )
    assert linked_story.id == story.id and artifact.source == "COPADO"


async def test_ingest_unknown_story_raises(session, adapter):
    await _seed_story(session, adapter)
    from app.services.workflow import NotFoundError
    with pytest.raises(NotFoundError):
        await copado_service.ingest_result(
            session, result_type="commit", payload={"components": []},
            jira_key="WLTH-DOES-NOT-EXIST",
        )


async def test_fixtures_full_run_ingests_three_artifacts(session, adapter):
    story = await _seed_story(session, adapter)
    for result in fixtures.sample_results("UAT"):
        await copado_service.ingest_result(
            session, result_type=result["result_type"], payload=result["payload"],
            jira_key="WLTH-101", copado_user_story_id="US-DEMO", run=result.get("run"),
        )
    await session.flush()
    arts = await artifact_service.list_artifacts(session, story.id)
    kinds = {a.kind for a in arts if a.source == "COPADO"}
    assert kinds == {ArtifactKind.SARIF, ArtifactKind.JUNIT, ArtifactKind.METADATA}


# ------------------------------------------------------------------ webhook auth


def test_authenticate_demo_mode_is_open():
    env = config.Settings(_env_file=None, demo_mode=True)
    copado_api._authenticate(env, None)  # no raise


def test_authenticate_missing_secret_is_503():
    env = config.Settings(_env_file=None, demo_mode=False, copado_webhook_secret="")
    with pytest.raises(HTTPException) as exc:
        copado_api._authenticate(env, "anything")
    assert exc.value.status_code == 503


def test_authenticate_wrong_signature_is_401():
    env = config.Settings(_env_file=None, demo_mode=False, copado_webhook_secret="s3cret")
    with pytest.raises(HTTPException) as exc:
        copado_api._authenticate(env, "wrong")
    assert exc.value.status_code == 401


def test_authenticate_correct_signature_passes():
    env = config.Settings(_env_file=None, demo_mode=False, copado_webhook_secret="s3cret")
    copado_api._authenticate(env, "s3cret")  # no raise
