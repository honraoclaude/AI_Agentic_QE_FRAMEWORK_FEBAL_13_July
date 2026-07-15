"""Configurable Jira -> platform field mapping.

The mapping lives in app settings (editable on the settings screen); this
module turns a raw REST v3 issue payload into the normalized JiraStoryData
the rest of the app consumes. Acceptance criteria are supported both as a
custom field and embedded in the description under an 'Acceptance Criteria'
heading.
"""

import re
from datetime import datetime

from .adapter import JiraStoryData
from .adf import adf_to_text

DEFAULT_FIELD_MAPPINGS: dict = {
    "story_points": "customfield_10016",
    "sprint": "customfield_10020",
    # mode: "custom_field" (read field_id) or "description" (parse heading)
    "acceptance_criteria": {"mode": "description", "field_id": ""},
    "fca_impact": "customfield_10200",
    "cloud": "customfield_10201",
}

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$")
_AC_HEADING_RE = re.compile(r"^\s*(?:#+\s*)?acceptance\s+criteria\s*:?\s*$", re.I)
_SPRINT_NAME_RE = re.compile(r"name=([^,\]]+)")

_CLOUD_ALIASES = {
    "FSC": "FSC",
    "FINANCIAL SERVICES CLOUD": "FSC",
    "SALES": "SALES",
    "SALES CLOUD": "SALES",
    "MARKETING": "MARKETING",
    "MARKETING CLOUD": "MARKETING",
}


def _select_value(raw) -> str | None:
    """Jira select fields arrive as {'value': X} or {'name': X} or a string."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("value") or raw.get("name")
    if raw is None:
        return None
    return str(raw).strip()


def _normalize_fca(raw) -> str | None:
    value = _select_value(raw)
    if value and value.upper() in ("LOW", "MEDIUM", "HIGH"):
        return value.upper()
    return None


def _normalize_cloud(raw) -> str | None:
    value = _select_value(raw)
    if not value:
        return None
    return _CLOUD_ALIASES.get(value.upper())


def _parse_sprint(raw) -> str | None:
    """Sprint fields vary: list of dicts (modern), list of legacy toString
    strings, a single dict, or a plain string."""
    if raw is None:
        return None
    if isinstance(raw, list):
        if not raw:
            return None
        # Prefer the active sprint, else the last one listed.
        dicts = [s for s in raw if isinstance(s, dict)]
        if dicts:
            active = [s for s in dicts if str(s.get("state", "")).lower() == "active"]
            return (active[-1] if active else dicts[-1]).get("name")
        raw = raw[-1]
    if isinstance(raw, dict):
        return raw.get("name")
    match = _SPRINT_NAME_RE.search(str(raw))
    return match.group(1).strip() if match else str(raw)


def _parse_datetime(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f%z")


def extract_ac_from_text(text: str) -> list[str]:
    """Pull bullet items that follow an 'Acceptance Criteria' heading line."""
    criteria: list[str] = []
    in_section = False
    for line in text.splitlines():
        if _AC_HEADING_RE.match(line):
            in_section = True
            continue
        if not in_section:
            continue
        if not line.strip():
            if criteria:
                break  # blank line after collected bullets ends the section
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            criteria.append(bullet.group(1).strip())
        elif criteria:
            break  # non-bullet line ends the section
    return criteria


def _extract_acceptance_criteria(fields: dict, description_text: str, mapping: dict) -> list[str]:
    ac_cfg = mapping.get("acceptance_criteria") or {}
    mode = ac_cfg.get("mode", "description")
    if mode == "custom_field" and ac_cfg.get("field_id"):
        raw = fields.get(ac_cfg["field_id"])
        if raw is not None:
            if isinstance(raw, list):
                return [str(item).strip() for item in raw if str(item).strip()]
            text = adf_to_text(raw)
            bullets = extract_ac_from_text("Acceptance Criteria\n" + text)
            if bullets:
                return bullets
            return [ln.strip("-*• ").strip() for ln in text.splitlines() if ln.strip()]
        # Custom field empty -> fall through to description parsing.
    return extract_ac_from_text(description_text)


def parse_issue(issue: dict, mapping: dict | None = None) -> JiraStoryData:
    mapping = mapping or DEFAULT_FIELD_MAPPINGS
    fields = issue.get("fields", {})

    description_text = adf_to_text(fields.get("description")).strip() or None
    assignee = fields.get("assignee") or {}
    status = fields.get("status") or {}
    priority = fields.get("priority") or {}

    points_raw = fields.get(mapping.get("story_points", ""))
    story_points = float(points_raw) if points_raw is not None else None

    return JiraStoryData(
        key=issue["key"],
        summary=fields.get("summary") or "",
        description=description_text,
        acceptance_criteria=_extract_acceptance_criteria(
            fields, description_text or "", mapping
        ),
        story_points=story_points,
        sprint=_parse_sprint(fields.get(mapping.get("sprint", ""))),
        status=status.get("name"),
        assignee=assignee.get("displayName"),
        labels=fields.get("labels") or [],
        priority=priority.get("name"),
        fca_impact=_normalize_fca(fields.get(mapping.get("fca_impact", ""))),
        cloud=_normalize_cloud(fields.get(mapping.get("cloud", ""))),
        updated_at=_parse_datetime(fields["updated"]),
    )


def fields_param(mapping: dict) -> list[str]:
    """The `fields` list to request from the search endpoint."""
    base = ["summary", "description", "status", "assignee", "labels", "priority", "updated"]
    for key in ("story_points", "sprint", "fca_impact", "cloud"):
        field_id = mapping.get(key)
        if field_id:
            base.append(field_id)
    ac_cfg = mapping.get("acceptance_criteria") or {}
    if ac_cfg.get("mode") == "custom_field" and ac_cfg.get("field_id"):
        base.append(ac_cfg["field_id"])
    return base
