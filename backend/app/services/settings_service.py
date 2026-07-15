"""Runtime settings (settings screen backend).

Non-secret configuration lives in the app_settings table and is editable via
the API; secrets (Jira token, Anthropic key) stay in .env and are only ever
reported as present/absent. Every update writes an audit event with the patch.
"""

import copy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import AppSetting
from . import audit
from .jira.field_mapping import DEFAULT_FIELD_MAPPINGS


def _default_gate(label: str) -> dict:
    return {
        "auto_post_comment": True,   # sign-off itself was the human approval
        "apply_label": True,
        "label": label,
        "transition_name": None,     # e.g. "Ready for Dev" — resolved dynamically
    }


DEFAULT_SETTINGS: dict = {
    "jira": {"project_key": "WLTH", "board_id": 0, "jql_override": ""},
    "platform": {"base_url": "http://localhost:5173"},
    "field_mappings": DEFAULT_FIELD_MAPPINGS,
    "gates": {
        "REFINEMENT": _default_gate("qe-gate-1-passed"),
        "DEVELOPMENT": _default_gate("qe-gate-2-passed"),
        "TESTING": _default_gate("qe-gate-3-passed"),
        "RELEASE": {**_default_gate("qe-gate-4-passed"), "attach_evidence": True},
    },
    "sync": {"enabled": False, "interval_minutes": 15},
}

_UPDATABLE_KEYS = set(DEFAULT_SETTINGS.keys())


def _deep_merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


async def get_all(session: AsyncSession) -> dict:
    """Defaults deep-merged with anything stored in the DB."""
    rows = (await session.execute(select(AppSetting))).scalars().all()
    stored = {row.key: row.value for row in rows}
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for key, value in stored.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


async def update_settings(session: AsyncSession, patch: dict, actor: str) -> dict:
    unknown = set(patch.keys()) - _UPDATABLE_KEYS
    if unknown:
        raise ValueError(f"unknown settings keys: {sorted(unknown)}")

    before = await get_all(session)
    for key, value in patch.items():
        row = await session.get(AppSetting, key)
        current = row.value if row else {}
        new_value = (
            _deep_merge(current, value)
            if isinstance(value, dict) and isinstance(current, dict)
            else value
        )
        if row:
            row.value = new_value
        else:
            session.add(AppSetting(key=key, value=new_value))
    await session.flush()
    after = await get_all(session)

    await audit.record_event(
        session,
        event_type="SETTINGS_UPDATED",
        entity_type="settings",
        entity_id=",".join(sorted(patch.keys())),
        actor=actor,
        payload={
            "patch": patch,
            "before": {k: before.get(k) for k in patch},
            "after": {k: after.get(k) for k in patch},
        },
    )
    return after


def env_summary() -> dict:
    """Read-only, secret-safe view of .env-held config for the settings screen."""
    env = get_settings()
    return {
        "demo_mode": env.demo_mode,
        "jira_base_url": env.jira_base_url,
        "jira_email": env.jira_email,
        "jira_api_token_set": bool(env.jira_api_token),
        "anthropic_api_key_set": bool(env.anthropic_api_key),
        "reasoning_model": env.reasoning_model,
        "classification_model": env.classification_model,
    }
