"""Real GitHub REST adapter (exercised when GITHUB_ENABLED + a token are set).

Demo-first build: changed files -> METADATA, changed source -> GENERIC, and
code-scanning SARIF are implemented against the public REST API; pulling JUnit /
coverage from Actions artifacts (which are zipped) is left as a documented
extension and simply omitted if unavailable — the flow degrades gracefully.
"""

import base64
import json

import httpx

from ...config import Settings
from ...models import ArtifactKind
from .adapter import GithubAdapter, PullItem

_SOURCE_EXT = (".cls", ".trigger", ".js", ".ts", ".html")
_MAX_SOURCE_FILES = 3


class GithubApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        super().__init__(f"GitHub API {status_code}: {detail}")


class RestGithubAdapter(GithubAdapter):
    def __init__(self, env: Settings):
        self._base = env.github_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {env.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _get(self, client: httpx.AsyncClient, path: str, **kwargs):
        r = await client.get(f"{self._base}{path}", headers=self._headers, **kwargs)
        if r.status_code >= 400:
            raise GithubApiError(r.status_code, r.text[:200])
        return r

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await self._get(client, "/rate_limit")
            return {"ok": True, "rate": r.json().get("rate", {})}

    async def get_branch(self, repo: str, branch: str) -> dict | None:
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                r = await self._get(client, f"/repos/{repo}/branches/{branch}")
            except GithubApiError as exc:
                if exc.status_code == 404:
                    return None
                raise
            data = r.json()
            return {"name": data["name"], "head_sha": data["commit"]["sha"], "repo": repo}

    async def fetch_branch_artifacts(self, repo: str, branch: str) -> list[PullItem]:
        base = f"{repo}@{branch}"
        items: list[PullItem] = []
        async with httpx.AsyncClient(timeout=30) as client:
            head = await self._get(client, f"/repos/{repo}/branches/{branch}")
            sha = head.json()["commit"]["sha"]
            commit = (await self._get(client, f"/repos/{repo}/commits/{sha}")).json()
            files = commit.get("files", []) or []

            components = [f["filename"] for f in files]
            items.append(PullItem(
                ArtifactKind.METADATA, "changed-files.json",
                json.dumps(components), f"{base} (diff {sha[:7]})",
            ))

            for f in [x for x in files if x["filename"].endswith(_SOURCE_EXT)][:_MAX_SOURCE_FILES]:
                try:
                    c = (await self._get(
                        client, f"/repos/{repo}/contents/{f['filename']}",
                        params={"ref": branch})).json()
                    text = base64.b64decode(c.get("content", "")).decode("utf-8", "replace")
                    items.append(PullItem(
                        ArtifactKind.GENERIC, f["filename"].split("/")[-1], text, f"{base} (source)"))
                except (GithubApiError, ValueError):
                    continue

            # Code-scanning SARIF (CodeQL etc.), best-effort.
            try:
                analyses = (await self._get(
                    client, f"/repos/{repo}/code-scanning/analyses",
                    params={"ref": f"refs/heads/{branch}", "per_page": 1})).json()
                if analyses:
                    aid = analyses[0]["id"]
                    sarif = await client.get(
                        f"{self._base}/repos/{repo}/code-scanning/analyses/{aid}",
                        headers={**self._headers, "Accept": "application/sarif+json"})
                    if sarif.status_code < 400:
                        items.append(PullItem(
                            ArtifactKind.SARIF, "code-scanning.sarif", sarif.text,
                            f"{base} (code-scanning {aid})"))
            except GithubApiError:
                pass

        return items
