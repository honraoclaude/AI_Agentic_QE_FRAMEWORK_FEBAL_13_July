"""GithubAdapter interface.

The mock adapter (demo mode) and the real REST adapter are interchangeable
behind this contract. A branch "pull" yields a flat list of PullItems — each
already tagged with the platform ArtifactKind and carrying raw text the existing
artifact parsers understand — so the ingest service treats GitHub, Copado and
manual uploads identically.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ...models import ArtifactKind


@dataclass
class PullItem:
    kind: ArtifactKind
    filename: str
    text: str
    ref: str  # provenance, e.g. "acme/wealth-sfdx@feature/WLTH-101 (CI #128)"


class GithubAdapter(ABC):
    @abstractmethod
    async def test_connection(self) -> dict:
        """Returns {'ok': bool, ...diagnostics}."""

    @abstractmethod
    async def get_branch(self, repo: str, branch: str) -> dict | None:
        """Branch head info: {name, head_sha, ...} or None if not found."""

    @abstractmethod
    async def fetch_branch_artifacts(self, repo: str, branch: str) -> list[PullItem]:
        """Pull the branch's changed files (-> METADATA), latest CI results
        (-> SARIF / JUNIT / COVERAGE) and a sample of changed source
        (-> GENERIC), as a list of PullItems ready to parse and store."""
