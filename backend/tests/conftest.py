import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app import config
from app import models  # noqa: F401 — register mappings
from app.database import Base, create_schema
from app.services.agents import engine as agent_engine
from app.services.jira.mock_adapter import MockJiraAdapter


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Tests must be hermetic: never read a developer's .env, never hold an
    API key (so the engine takes the stub path unless a test opts in)."""
    settings = config.Settings(_env_file=None)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_engine, "get_settings", lambda: settings)
    return settings


@pytest.fixture
async def engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await create_schema(conn)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
def adapter():
    return MockJiraAdapter()
