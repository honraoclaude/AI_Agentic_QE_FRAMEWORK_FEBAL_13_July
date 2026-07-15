from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Secrets come from .env only — never the DB."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    database_url: str = "sqlite+aiosqlite:///./pact_qe.db"
    demo_mode: bool = True

    # Anthropic (agent engine — Step 3)
    anthropic_api_key: str = ""
    reasoning_model: str = "claude-sonnet-4-6"
    classification_model: str = "claude-haiku-4-5"

    # Jira (real REST adapter — Step 2)
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "WLTH"
    jira_board_id: int = 0
    jira_jql_override: str = ""
    sync_enabled: bool = False
    sync_interval_minutes: int = 15

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
