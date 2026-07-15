import json

import httpx
import pytest

from app.config import Settings
from app.services.jira.adf import adf_to_text, doc, heading, paragraph
from app.services.jira.field_mapping import (
    DEFAULT_FIELD_MAPPINGS,
    extract_ac_from_text,
    parse_issue,
)
from app.services.jira.rest_adapter import JiraApiError, RestJiraAdapter

ENV = Settings(
    demo_mode=False,
    jira_base_url="https://wealthco.atlassian.net",
    jira_email="lead@wealthco.example",
    jira_api_token="token-123",
    _env_file=None,
)


def _adf_description() -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "As an advisor I want a rollup."}
                ],
            },
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Acceptance Criteria"}],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Sums active accounts"}
                                ],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "Excludes closed accounts"}
                                ],
                            }
                        ],
                    },
                ],
            },
        ],
    }


def _issue_json(key: str = "WLTH-201") -> dict:
    return {
        "key": key,
        "fields": {
            "summary": "Household rollup",
            "description": _adf_description(),
            "status": {"name": "Refinement"},
            "assignee": {"displayName": "Priya Sharma"},
            "labels": ["fsc"],
            "priority": {"name": "High"},
            "updated": "2026-07-10T09:15:00.000+0000",
            "customfield_10016": 8.0,
            "customfield_10020": [
                {"id": 5, "name": "Sprint 23", "state": "closed"},
                {"id": 6, "name": "Sprint 24", "state": "active"},
            ],
            "customfield_10200": {"value": "High"},
            "customfield_10201": {"value": "Financial Services Cloud"},
        },
    }


# ------------------------------------------------------------- pure parsing


def test_adf_roundtrip_text_extraction():
    body = doc(heading("Title", 3), paragraph("Hello world"))
    text = adf_to_text(body)
    assert "Title" in text and "Hello world" in text


def test_extract_ac_from_plain_text():
    text = (
        "Some context line.\n\n"
        "Acceptance Criteria\n"
        "- first criterion\n"
        "* second criterion\n"
        "1. third criterion\n"
        "\n"
        "Notes: unrelated\n"
    )
    assert extract_ac_from_text(text) == [
        "first criterion",
        "second criterion",
        "third criterion",
    ]


def test_parse_issue_maps_all_fields():
    story = parse_issue(_issue_json(), DEFAULT_FIELD_MAPPINGS)
    assert story.key == "WLTH-201"
    assert story.summary == "Household rollup"
    assert "As an advisor" in story.description
    # AC parsed out of the ADF description section.
    assert story.acceptance_criteria == [
        "Sums active accounts",
        "Excludes closed accounts",
    ]
    assert story.story_points == 8.0
    assert story.sprint == "Sprint 24"  # active sprint wins
    assert story.status == "Refinement"
    assert story.assignee == "Priya Sharma"
    assert story.priority == "High"
    assert story.fca_impact == "HIGH"       # normalized from 'High'
    assert story.cloud == "FSC"             # normalized from 'Financial Services Cloud'
    assert story.updated_at.year == 2026


def test_parse_issue_ac_custom_field_mode():
    mapping = {
        **DEFAULT_FIELD_MAPPINGS,
        "acceptance_criteria": {"mode": "custom_field", "field_id": "customfield_10100"},
    }
    issue = _issue_json()
    issue["fields"]["customfield_10100"] = "- given a thing\n- when acted on"
    story = parse_issue(issue, mapping)
    assert story.acceptance_criteria == ["given a thing", "when acted on"]


def test_parse_issue_legacy_sprint_string():
    issue = _issue_json()
    issue["fields"]["customfield_10020"] = [
        "com.atlassian.greenhopper.service.sprint.Sprint@1f[id=6,state=ACTIVE,name=Sprint 24,goal=]"
    ]
    story = parse_issue(issue, DEFAULT_FIELD_MAPPINGS)
    assert story.sprint == "Sprint 24"


# --------------------------------------------------------------- HTTP layer


def _adapter_with(handler) -> RestJiraAdapter:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RestJiraAdapter(env=ENV, client=client)


async def test_fetch_stories_paginates_with_next_page_token():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        assert request.url.path == "/rest/api/3/search/jql"
        assert request.headers.get("authorization", "").startswith("Basic ")
        if "nextPageToken" not in request.url.params:
            return httpx.Response(
                200,
                json={"issues": [_issue_json("WLTH-201")], "nextPageToken": "tok2"},
            )
        return httpx.Response(200, json={"issues": [_issue_json("WLTH-202")]})

    adapter = _adapter_with(handler)
    stories = await adapter.fetch_stories()
    assert [s.key for s in stories] == ["WLTH-201", "WLTH-202"]
    assert len(calls) == 2
    assert calls[1]["nextPageToken"] == "tok2"
    # Default JQL targets the configured project's open sprint.
    assert 'project = "WLTH"' in calls[0]["jql"]


async def test_fetch_story_404_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"errorMessages": ["Issue does not exist"]})

    adapter = _adapter_with(handler)
    assert await adapter.fetch_story("WLTH-999") is None


async def test_add_comment_and_error_surface():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comment"):
            body = json.loads(request.content)
            assert body["body"]["type"] == "doc"
            return httpx.Response(201, json={"id": "10001"})
        return httpx.Response(500, text="boom")

    adapter = _adapter_with(handler)
    result = await adapter.add_comment("WLTH-201", doc(paragraph("hi")))
    assert result == {"ok": True, "comment_id": "10001"}

    with pytest.raises(JiraApiError) as excinfo:
        await adapter.add_label("WLTH-201", "qe-gate-1-passed")
    assert excinfo.value.status_code == 500


async def test_transitions_fetched_dynamically():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "transitions": [
                        {"id": "31", "name": "Ready for UAT", "to": {"name": "UAT"}}
                    ]
                },
            )
        body = json.loads(request.content)
        assert body == {"transition": {"id": "31"}}
        return httpx.Response(204)

    adapter = _adapter_with(handler)
    transitions = await adapter.get_transitions("WLTH-201")
    assert transitions == [{"id": "31", "name": "Ready for UAT"}]
    result = await adapter.transition_issue("WLTH-201", "31")
    assert result["ok"] is True


async def test_test_connection_reports_failure_not_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    adapter = _adapter_with(handler)
    result = await adapter.test_connection()
    assert result["ok"] is False
    assert "401" in result["error"]
