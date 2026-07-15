"""Versioned prompt registry — prompts are files, not code.

Layout: backend/prompts/<agent_key>/<version>.md
The registry (registry.py) pins each agent to a prompt version; bumping a
prompt = adding a new file and updating the pin, so every historical run's
prompt_version in the audit trail resolves to the exact text used.
"""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


class PromptNotFoundError(Exception):
    pass


@lru_cache(maxsize=128)
def load_prompt(agent_key: str, version: str) -> str:
    path = PROMPTS_DIR / agent_key / f"{version}.md"
    if not path.is_file():
        raise PromptNotFoundError(
            f"prompt file missing: {path} (agent={agent_key}, version={version})"
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PromptNotFoundError(f"prompt file is empty: {path}")
    return text


def available_versions(agent_key: str) -> list[str]:
    folder = PROMPTS_DIR / agent_key
    if not folder.is_dir():
        return []
    return sorted(p.stem for p in folder.glob("v*.md"))
