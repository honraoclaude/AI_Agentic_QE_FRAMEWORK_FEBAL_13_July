from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.enums import (
    Cloud,
    FcaImpact,
    GateStatus,
    Phase,
    PushStatus,
    PushType,
    RunStatus,
    ScopeStatus,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- responses


class RunOut(ORMModel):
    id: str
    story_id: str
    agent_key: str
    phase: Phase
    sequence: int
    attempt: int
    status: RunStatus
    prompt_version: str
    model: str | None
    input_hash: str | None
    input_json: dict | None
    output_json: dict | None
    output_hash: str | None
    token_usage: dict | None
    guidance: str | None
    parent_run_id: str | None
    approved_by: str | None
    decided_by: str | None
    decision_reason: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    decided_at: datetime | None


class RunSummaryOut(ORMModel):
    """Lightweight run view for board cards (progress dots)."""

    id: str
    agent_key: str
    phase: Phase
    sequence: int
    attempt: int
    status: RunStatus


class GateOut(ORMModel):
    id: str
    story_id: str
    phase: Phase
    status: GateStatus
    approver_name: str | None
    approver_role: str | None
    rationale: str | None
    evidence: dict | None
    created_at: datetime
    decided_at: datetime | None


class StoryOut(ORMModel):
    id: str
    jira_key: str
    summary: str
    description: str | None
    acceptance_criteria: list
    story_points: float | None
    sprint: str | None
    jira_status: str | None
    assignee: str | None
    labels: list
    priority: str | None
    fca_impact: FcaImpact | None
    fca_impact_confirmed: bool
    cloud: Cloud | None
    current_phase: Phase
    scope_status: ScopeStatus
    released: bool
    copado_user_story_id: str | None = None
    github_repo: str | None = None
    github_branch: str | None = None
    jira_updated_at: datetime | None
    last_synced_at: datetime | None
    changed_since_agent_run: bool
    created_at: datetime
    updated_at: datetime


class StoryBoardOut(StoryOut):
    """Board payload: story + current runs (latest attempt per agent) + gates."""

    runs: list[RunSummaryOut] = Field(default_factory=list)
    gates: list[GateOut] = Field(default_factory=list)


class StoryDetailOut(StoryOut):
    runs: list[RunOut] = Field(default_factory=list)
    gates: list[GateOut] = Field(default_factory=list)


class AuditEventOut(ORMModel):
    id: int
    event_type: str
    entity_type: str
    entity_id: str
    actor: str
    payload: dict
    payload_hash: str
    prev_hash: str
    event_hash: str
    created_at: str


class SyncResultOut(BaseModel):
    total: int
    created: int
    updated: int
    unchanged: int
    out_of_scope: int
    flagged_conflicts: list[str]


# ---------------------------------------------------------------- requests


class ApproveRequest(BaseModel):
    approver: str = Field(min_length=1, max_length=128)


class AcceptRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)


# Free-text fields are bounded so a client can't push unbounded payloads
# into the DB / audit trail. 4000 chars is generous for a reason/rationale.
FREETEXT_MAX = 4000


class RejectRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=FREETEXT_MAX)


class RerunRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)
    guidance: str = Field(min_length=1, max_length=FREETEXT_MAX)


class GateDecisionRequest(BaseModel):
    approver_name: str = Field(min_length=1, max_length=128)
    approver_role: str = Field(min_length=1, max_length=64)
    rationale: str = Field(min_length=1, max_length=FREETEXT_MAX)


class SyncRequest(BaseModel):
    actor: str = Field(default="system", max_length=128)
    jql: str | None = Field(default=None, max_length=2000)


# ------------------------------------------------------------------- push


class PushItemOut(ORMModel):
    id: str
    story_id: str
    push_type: PushType
    status: PushStatus
    payload: dict
    approved_by: str | None
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class DraftPushRequest(BaseModel):
    kind: str = Field(pattern="^(agent_summary|bdd_scenarios)$")
    run_id: str
    actor: str = Field(min_length=1, max_length=128)


class PushActionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=128)


# --------------------------------------------------------------- settings


class SettingsOut(BaseModel):
    env: dict  # read-only, secret-safe (.env-held config)
    settings: dict  # DB-held, editable


class SettingsUpdateRequest(BaseModel):
    actor: str = Field(default="system", max_length=128)
    patch: dict = Field(min_length=1)
