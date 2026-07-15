"""Role-based work queue.

Aggregates every pending human touchpoint and filters it to what a given role
is responsible for, so each role gets a focused "My Work" view.

Responsibility model (grounded in the gate approval matrix):

- Gate sign-offs are role-specific approvals:
    Gate 1 Refinement  -> Product Owner + QE Lead
    Gate 2 Development  -> Tech Lead
    Gate 3 Testing      -> QE Lead
    Gate 4 Release      -> Product Owner + Business Stakeholder
                           (+ Compliance Officer when FCA impact is HIGH /
                            unclassified — precautionary, matching the UAT
                            Sign-Off Coordinator policy)
- Pipeline operator actions (approve & run agents, accept/reject completed
  runs, approve/retry Jira pushes) belong to the QE Lead who drives the
  pipeline.

This is a read/aggregation view — it does NOT restrict who may act (the board
and push queue still allow any named user to act). It answers "what is waiting
on my role?".
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AgentRun,
    FcaImpact,
    Gate,
    GateStatus,
    PHASE_ORDER,
    Phase,
    PushQueueItem,
    PushStatus,
    RunStatus,
    ScopeStatus,
    Story,
)
from .agents.registry import AGENTS

ROLES: list[str] = [
    "Product Owner",
    "Tech Lead",
    "QE Lead",
    "Business Stakeholder",
    "Compliance Officer",
]

GATE_SIGNERS: dict[Phase, set[str]] = {
    Phase.REFINEMENT: {"Product Owner", "QE Lead"},
    Phase.DEVELOPMENT: {"Tech Lead"},
    Phase.TESTING: {"QE Lead"},
    Phase.RELEASE: {"Product Owner", "Business Stakeholder"},
}

# Roles that operate the agent pipeline + Jira pushes.
OPERATOR_ROLES: set[str] = {"QE Lead"}


def is_valid_role(role: str) -> bool:
    return role in ROLES


def gate_signer_roles(phase: Phase, story: Story) -> set[str]:
    signers = set(GATE_SIGNERS.get(phase, set()))
    # Compliance Officer required for Release when FCA impact is HIGH; an
    # unclassified story is treated as HIGH until confirmed (precautionary).
    if phase == Phase.RELEASE and (
        story.fca_impact == FcaImpact.HIGH or story.fca_impact is None
    ):
        signers.add("Compliance Officer")
    return signers


def _agent_name(agent_key: str) -> str:
    agent = AGENTS.get(agent_key)
    return agent.name if agent else agent_key


def _phase_rank(phase: Phase) -> int:
    return PHASE_ORDER.index(phase)


async def get_work(session: AsyncSession, role: str) -> dict:
    """Return the pending work items relevant to `role`."""
    items: list[dict] = []

    # --- Gate sign-offs (role-specific approvals) ---
    gate_rows = (
        await session.execute(
            select(Gate, Story)
            .join(Story, Gate.story_id == Story.id)
            .where(
                Gate.status == GateStatus.READY_FOR_SIGNOFF,
                Story.scope_status == ScopeStatus.ACTIVE,
            )
        )
    ).all()
    for gate, story in gate_rows:
        signers = gate_signer_roles(gate.phase, story)
        if role not in signers:
            continue
        gate_no = _phase_rank(gate.phase) + 1
        reason = f"Gate {gate_no} sign-off requires: {', '.join(sorted(signers))}"
        if gate.phase == Phase.RELEASE and "Compliance Officer" in signers:
            reason += (
                f" (FCA impact {story.fca_impact.value if story.fca_impact else 'unclassified'})"
            )
        items.append(
            {
                "kind": "GATE_SIGNOFF",
                "action": "SIGN_GATE",
                "story_id": story.id,
                "jira_key": story.jira_key,
                "story_summary": story.summary,
                "phase": gate.phase.value,
                "entity_id": gate.id,
                "title": f"Sign off Gate {gate_no} — {gate.phase.value.title()}",
                "detail": "Ready for sign-off; evidence checklist complete.",
                "reason": reason,
                "since": gate.created_at.isoformat() if gate.created_at else None,
            }
        )

    # --- Operator actions: agent runs + Jira pushes ---
    if role in OPERATOR_ROLES:
        run_rows = (
            await session.execute(
                select(AgentRun, Story)
                .join(Story, AgentRun.story_id == Story.id)
                .where(
                    AgentRun.status.in_(
                        [RunStatus.AWAITING_APPROVAL, RunStatus.COMPLETED]
                    ),
                    Story.scope_status == ScopeStatus.ACTIVE,
                )
            )
        ).all()
        for run, story in run_rows:
            name = _agent_name(run.agent_key)
            if run.status == RunStatus.AWAITING_APPROVAL:
                items.append(
                    {
                        "kind": "RUN_APPROVAL",
                        "action": "APPROVE_RUN",
                        "story_id": story.id,
                        "jira_key": story.jira_key,
                        "story_summary": story.summary,
                        "phase": run.phase.value,
                        "entity_id": run.id,
                        "title": f"Approve & Run: {name}",
                        "detail": "No agent runs without your explicit approval.",
                        "reason": "QE Lead operates the agent pipeline",
                        "since": run.created_at.isoformat() if run.created_at else None,
                    }
                )
            else:  # COMPLETED — awaiting Accept / Reject / Re-run
                blocking = bool((run.output_json or {}).get("release_blocking"))
                items.append(
                    {
                        "kind": "RUN_DECISION",
                        "action": "DECIDE_RUN",
                        "story_id": story.id,
                        "jira_key": story.jira_key,
                        "story_summary": story.summary,
                        "phase": run.phase.value,
                        "entity_id": run.id,
                        "title": f"Review output: {name}",
                        "detail": (
                            "Release-blocking finding — resolve before the gate can pass."
                            if blocking
                            else "Accept, reject, or re-run with guidance."
                        ),
                        "reason": "QE Lead reviews agent output",
                        "since": run.completed_at.isoformat()
                        if run.completed_at
                        else None,
                    }
                )

        push_rows = (
            await session.execute(
                select(PushQueueItem, Story)
                .join(Story, PushQueueItem.story_id == Story.id)
                .where(
                    PushQueueItem.status.in_([PushStatus.DRAFT, PushStatus.FAILED])
                )
            )
        ).all()
        for push, story in push_rows:
            if push.status == PushStatus.DRAFT:
                items.append(
                    {
                        "kind": "PUSH_APPROVAL",
                        "action": "APPROVE_PUSH",
                        "story_id": story.id,
                        "jira_key": story.jira_key,
                        "story_summary": story.summary,
                        "phase": None,
                        "entity_id": push.id,
                        "title": f"Approve Jira push: {push.push_type.value}",
                        "detail": "Preview and approve before it posts to Jira.",
                        "reason": "QE Lead approves outbound Jira posts",
                        "since": push.created_at.isoformat()
                        if push.created_at
                        else None,
                    }
                )
            else:  # FAILED
                items.append(
                    {
                        "kind": "PUSH_RETRY",
                        "action": "RETRY_PUSH",
                        "story_id": story.id,
                        "jira_key": story.jira_key,
                        "story_summary": story.summary,
                        "phase": None,
                        "entity_id": push.id,
                        "title": f"Retry failed Jira push: {push.push_type.value}",
                        "detail": push.last_error or "Send failed — retry.",
                        "reason": "QE Lead clears the push retry queue",
                        "since": push.updated_at.isoformat()
                        if push.updated_at
                        else None,
                    }
                )

    # Sort: gates first (most actionable), then by phase order, then story.
    kind_rank = {
        "GATE_SIGNOFF": 0,
        "RUN_DECISION": 1,
        "RUN_APPROVAL": 2,
        "PUSH_RETRY": 3,
        "PUSH_APPROVAL": 4,
    }
    items.sort(
        key=lambda i: (
            kind_rank.get(i["kind"], 9),
            _phase_rank(Phase(i["phase"])) if i["phase"] else 9,
            i["jira_key"],
        )
    )

    counts: dict[str, int] = {}
    for item in items:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1

    return {"role": role, "roles": ROLES, "items": items, "counts": counts}
