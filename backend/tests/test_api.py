"""End-to-end HTTP tests through the real ASGI app: validation caps, the
exception-handler mapping (404 / 409 / 502 / 500), and a wired happy path."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import get_session
from app.main import app
from app.services.jira import factory
from app.services.jira.rest_adapter import JiraApiError


@pytest.fixture
async def client(engine):
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    factory.reset_adapter()
    # raise_app_exceptions=False so the test observes the clean 500 response
    # the handler sends to the client (Starlette also re-raises 500s so the
    # ASGI server can log them — that is production-correct, just not what we
    # want to assert on here).
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    factory.reset_adapter()


async def _seed(client: AsyncClient) -> list[dict]:
    await client.post("/api/v1/demo/seed")
    return (await client.get("/api/v1/stories")).json()


# --------------------------------------------------------------- validation


async def test_oversized_reason_rejected_422(client):
    res = await client.post(
        "/api/v1/runs/whatever/reject",
        json={"actor": "x", "reason": "z" * 5000},
    )
    assert res.status_code == 422  # bounded before the handler even runs


async def test_blank_actor_rejected_422(client):
    res = await client.post("/api/v1/runs/whatever/approve", json={"approver": ""})
    assert res.status_code == 422


# ------------------------------------------------------ exception mapping


async def test_missing_run_maps_to_404(client):
    res = await client.post(
        "/api/v1/runs/nonexistent/approve", json={"approver": "Test Lead"}
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


async def test_out_of_sequence_approve_maps_to_409(client):
    stories = await _seed(client)
    story = next(s for s in stories if s["jira_key"] == "WLTH-101")
    locked = next(r for r in story["runs"] if r["status"] == "PROPOSED")
    res = await client.post(
        f"/api/v1/runs/{locked['id']}/approve", json={"approver": "Test Lead"}
    )
    assert res.status_code == 409
    assert "AWAITING_APPROVAL" in res.json()["detail"]


async def test_jira_upstream_error_maps_to_502(client, monkeypatch):
    async def raise_jira(*args, **kwargs):
        raise JiraApiError(503, "service unavailable")

    monkeypatch.setattr(factory._get_mock(), "fetch_stories", raise_jira)
    res = await client.post("/api/v1/jira/sync", json={"actor": "x"})
    assert res.status_code == 502
    assert "Jira request failed" in res.json()["detail"]
    assert "503" in res.json()["detail"]


async def test_unexpected_error_maps_to_clean_500(client, monkeypatch):
    async def explode(*args, **kwargs):
        raise RuntimeError("secret internal detail that must not leak")

    monkeypatch.setattr(factory._get_mock(), "fetch_stories", explode)
    res = await client.post("/api/v1/jira/sync", json={"actor": "x"})
    assert res.status_code == 500
    # Generic message only — no stack trace / internal string leaked.
    assert res.json() == {"detail": "internal server error"}


# ---------------------------------------------------------- wired happy path


async def test_http_approve_accept_flow(client):
    stories = await _seed(client)
    story = next(s for s in stories if s["jira_key"] == "WLTH-103")
    run = next(r for r in story["runs"] if r["status"] == "AWAITING_APPROVAL")

    approved = await client.post(
        f"/api/v1/runs/{run['id']}/approve", json={"approver": "Honra"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "COMPLETED"

    accepted = await client.post(
        f"/api/v1/runs/{run['id']}/accept", json={"actor": "Honra"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACCEPTED"

    # Chain still verifies through the HTTP surface.
    verify = await client.get("/api/v1/audit/verify")
    assert verify.json()["valid"] is True
