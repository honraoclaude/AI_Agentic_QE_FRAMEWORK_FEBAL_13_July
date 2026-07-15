from sqlalchemy.ext.asyncio import AsyncSession

from ...config import Settings, get_settings
from .adapter import JiraAdapter
from .mock_adapter import MockJiraAdapter

_mock: MockJiraAdapter | None = None


def _get_mock() -> MockJiraAdapter:
    """Singleton mock — keeps its in-memory state across requests in demo mode."""
    global _mock
    if _mock is None:
        _mock = MockJiraAdapter()
    return _mock


async def get_adapter(session: AsyncSession, env: Settings | None = None) -> JiraAdapter:
    """Demo mode (or missing Jira credentials) -> singleton mock adapter;
    otherwise a REST adapter configured with the current DB-held settings
    (project key, JQL override, field mappings)."""
    env = env or get_settings()
    if env.demo_mode or not env.jira_configured:
        return _get_mock()

    from .. import settings_service
    from .rest_adapter import RestJiraAdapter

    cfg = await settings_service.get_all(session)
    return RestJiraAdapter(
        env=env,
        jira_config=cfg.get("jira"),
        field_mappings=cfg.get("field_mappings"),
    )


def reset_adapter() -> None:
    """Test / settings-change hook."""
    global _mock
    _mock = None
