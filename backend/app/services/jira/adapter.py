"""JiraAdapter interface. The mock adapter (demo mode) and the real REST v3
adapter (Step 2) are interchangeable behind this contract — the sync and push
services only ever see this interface.
"""

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel, Field


class JiraStoryData(BaseModel):
    """A story normalized from Jira into the platform's field model.
    Field mapping (custom fields, AC-in-description parsing) happens inside
    the adapter, so the rest of the app never sees raw Jira payloads."""

    key: str
    summary: str
    description: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    story_points: float | None = None
    sprint: str | None = None
    status: str | None = None
    assignee: str | None = None
    labels: list[str] = Field(default_factory=list)
    priority: str | None = None
    fca_impact: str | None = None  # LOW/MEDIUM/HIGH if mapped in Jira
    cloud: str | None = None       # FSC/SALES/MARKETING if mapped in Jira
    updated_at: datetime


class JiraAdapter(ABC):
    @abstractmethod
    async def test_connection(self) -> dict:
        """Returns {'ok': bool, ...diagnostics}."""

    @abstractmethod
    async def fetch_stories(self, jql: str | None = None) -> list[JiraStoryData]:
        """Pull stories matching the JQL filter (default: configured sprint)."""

    @abstractmethod
    async def fetch_story(self, key: str) -> JiraStoryData | None:
        """Pull a single story by key (single-story refresh)."""

    # --- Push surface (implemented fully in Step 2) ---

    @abstractmethod
    async def add_comment(self, key: str, adf_body: dict) -> dict:
        """Post an Atlassian Document Format comment."""

    @abstractmethod
    async def add_label(self, key: str, label: str) -> dict: ...

    @abstractmethod
    async def get_transitions(self, key: str) -> list[dict]:
        """Fetch available transitions dynamically — never hardcode IDs."""

    @abstractmethod
    async def transition_issue(self, key: str, transition_id: str) -> dict: ...

    @abstractmethod
    async def attach_file(self, key: str, filename: str, content: bytes) -> dict: ...
