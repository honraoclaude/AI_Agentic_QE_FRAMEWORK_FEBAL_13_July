from ...config import Settings, get_settings
from .adapter import GithubAdapter
from .mock_adapter import MockGithubAdapter

_mock: MockGithubAdapter | None = None


def _get_mock() -> MockGithubAdapter:
    global _mock
    if _mock is None:
        _mock = MockGithubAdapter()
    return _mock


def get_adapter(env: Settings | None = None) -> GithubAdapter:
    """Demo mode (or no GitHub token) -> singleton mock; otherwise the REST
    adapter configured from .env."""
    env = env or get_settings()
    if env.demo_mode or not env.github_configured:
        return _get_mock()
    from .rest_adapter import RestGithubAdapter

    return RestGithubAdapter(env)


def reset_adapter() -> None:
    global _mock
    _mock = None
