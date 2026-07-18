"""Agent-run and gate state machines — the single source of truth for legal
transitions. The HITL non-negotiables are enforced HERE, server-side:

1. No agent ever starts without an explicit, recorded human approval.
2. Agents within a phase run in sequence; the next unlocks only on Accept.
3. A gate becomes READY_FOR_SIGNOFF only when every phase agent's latest run
   is ACCEPTED and no accepted run carries a release-blocking finding.
4. Release-blocking findings (FCA scenarios, Financial Data Integrity) have
   no override path — the gate simply never becomes ready.
5. Gate order is strict: sign-off advances the story exactly one phase.

Every transition writes an audit event in the same transaction.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    AGENT_UPSTREAM_INPUTS,
    AgentRun,
    Gate,
    GateStatus,
    PHASE_ORDER,
    Phase,
    RunStatus,
    Story,
    next_phase,
)
from ..util import utcnow
from . import audit
from . import settings_service
from .agents import engine
from .agents.registry import AgentDefinition, agents_for_phase, get_agent


class WorkflowError(Exception):
    """Illegal state transition or violated invariant. Maps to HTTP 409."""


class NotFoundError(Exception):
    """Entity does not exist. Maps to HTTP 404."""


# ---------------------------------------------------------------- helpers


async def _get_run(session: AsyncSession, run_id: str) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"agent run {run_id} not found")
    return run


async def _get_story(session: AsyncSession, story_id: str) -> Story:
    story = await session.get(Story, story_id)
    if story is None:
        raise NotFoundError(f"story {story_id} not found")
    return story


async def latest_run(
    session: AsyncSession, story_id: str, agent_key: str
) -> AgentRun | None:
    return (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.story_id == story_id, AgentRun.agent_key == agent_key)
            .order_by(AgentRun.attempt.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _gather_upstream(
    session: AsyncSession, story_id: str, agent_key: str
) -> list[dict]:
    """Return the accepted output of the upstream agents this agent consumes
    (e.g. BDD consumes the accepted Three Amigos example map + Story Quality
    AC gaps). Only ACCEPTED runs feed downstream."""
    out: list[dict] = []
    for upstream_key in AGENT_UPSTREAM_INPUTS.get(agent_key, []):
        run = (
            await session.execute(
                select(AgentRun)
                .where(
                    AgentRun.story_id == story_id,
                    AgentRun.agent_key == upstream_key,
                    AgentRun.status == RunStatus.ACCEPTED,
                )
                .order_by(AgentRun.attempt.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if run and run.output_json:
            out.append(
                {
                    "agent_key": upstream_key,
                    "agent_name": get_agent(upstream_key).name,
                    "output": run.output_json,
                }
            )
    return out


def _run_event_payload(run: AgentRun) -> dict:
    return {
        "run_id": run.id,
        "story_id": run.story_id,
        "agent_key": run.agent_key,
        "phase": run.phase.value,
        "attempt": run.attempt,
        "status": run.status.value,
    }


# ------------------------------------------------------ story bootstrap


async def ensure_story_workflow(
    session: AsyncSession, story: Story, actor: str = "system"
) -> None:
    """Create the four gates (all LOCKED) and propose the current phase's
    agents if they don't exist yet. Idempotent."""
    existing_gates = {
        g.phase
        for g in (
            await session.execute(select(Gate).where(Gate.story_id == story.id))
        ).scalars()
    }
    for phase in PHASE_ORDER:
        if phase not in existing_gates:
            session.add(Gate(story_id=story.id, phase=phase))
    await session.flush()

    await propose_phase_runs(session, story, story.current_phase, actor)


async def propose_phase_runs(
    session: AsyncSession, story: Story, phase: Phase, actor: str = "system"
) -> list[AgentRun]:
    """Propose the phase's agents in sequence. Nothing runs automatically:
    the first *active* agent is AWAITING_APPROVAL (unlocked for a human), the
    rest are PROPOSED (locked behind their predecessor's acceptance). Agents the
    org has disabled are recorded SKIPPED (blocking-capable agents are never
    disabled). Idempotent."""
    disabled = await settings_service.disabled_agents(session)
    created: list[AgentRun] = []
    first_active_assigned = False
    for agent in agents_for_phase(phase):
        if await latest_run(session, story.id, agent.key) is not None:
            continue
        skipped = agent.key in disabled and not agent.blocking_capable
        if skipped:
            status = RunStatus.SKIPPED
        elif not first_active_assigned:
            status = RunStatus.AWAITING_APPROVAL
            first_active_assigned = True
        else:
            status = RunStatus.PROPOSED
        run = AgentRun(
            story_id=story.id,
            agent_key=agent.key,
            phase=phase,
            sequence=agent.sequence,
            status=status,
            prompt_version=agent.prompt_version,
        )
        session.add(run)
        await session.flush()
        created.append(run)
        await audit.record_event(
            session,
            event_type="RUN_SKIPPED" if skipped else "RUN_PROPOSED",
            entity_type="agent_run",
            entity_id=run.id,
            actor="settings" if skipped else actor,
            payload=_run_event_payload(run),
        )
    # An all-skipped phase has no accept to trigger readiness — evaluate now.
    if created:
        await recompute_gate_readiness(session, story, actor)
    return created


# ------------------------------------------------------ agent run machine


async def approve_and_run(
    session: AsyncSession, run_id: str, approver: str
) -> AgentRun:
    """Human clicks Approve & Run. Records the approval, then executes."""
    if not approver or not approver.strip():
        raise WorkflowError("approver name is required — approvals must be attributable")
    run = await _get_run(session, run_id)
    if run.status != RunStatus.AWAITING_APPROVAL:
        raise WorkflowError(
            f"run is {run.status.value}; only AWAITING_APPROVAL runs can be approved"
        )
    story = await _get_story(session, run.story_id)
    agent = get_agent(run.agent_key)

    run.approved_by = approver.strip()
    run.status = RunStatus.RUNNING
    run.started_at = utcnow()
    await audit.record_event(
        session,
        event_type="RUN_APPROVED",
        entity_type="agent_run",
        entity_id=run.id,
        actor=run.approved_by,
        payload=_run_event_payload(run),
    )

    # Gather inputs: uploaded CI/CD artifacts this agent consumes, and the
    # accepted output of upstream agents it builds on (chained refinement).
    from .artifacts import service as artifact_service

    artifacts = await artifact_service.gather_for_agent(session, story.id, agent.key)
    upstream = await _gather_upstream(session, story.id, agent.key)
    try:
        result = await engine.execute(
            run,
            story,
            agent,
            guidance=run.guidance,
            artifacts=artifacts,
            upstream=upstream,
        )
    except Exception as exc:  # engine/API failure — never lose the record
        run.status = RunStatus.FAILED
        run.completed_at = utcnow()
        run.decision_reason = f"engine failure: {exc}"
        await audit.record_event(
            session,
            event_type="RUN_FAILED",
            entity_type="agent_run",
            entity_id=run.id,
            actor="system",
            payload={**_run_event_payload(run), "error": str(exc)},
        )
        return run

    run.status = RunStatus.COMPLETED
    run.completed_at = utcnow()
    # Re-stamp with the version that ACTUALLY executed: the row was stamped at
    # propose time, but the engine loads the current registry prompt — if the
    # prompt was upgraded in between, the audit record must reflect reality.
    run.prompt_version = agent.prompt_version
    run.output_json = result["output"]
    run.input_json = result["input"]
    run.output_hash = result["output_hash"]
    run.input_hash = result["input_hash"]
    run.model = result["model"]
    run.token_usage = result["token_usage"]
    await audit.record_event(
        session,
        event_type="RUN_COMPLETED",
        entity_type="agent_run",
        entity_id=run.id,
        actor="system",
        payload={
            **_run_event_payload(run),
            "model": run.model,
            "prompt_version": run.prompt_version,
            "input_hash": run.input_hash,
            "output_hash": run.output_hash,
            "token_usage": run.token_usage,
            "release_blocking": bool(run.output_json.get("release_blocking")),
        },
    )
    return run


async def accept_run(session: AsyncSession, run_id: str, actor: str) -> AgentRun:
    """Accept the output — unlocks the next agent in sequence, and may make
    the phase gate ready for sign-off."""
    if not actor or not actor.strip():
        raise WorkflowError("actor name is required")
    run = await _get_run(session, run_id)
    if run.status != RunStatus.COMPLETED:
        raise WorkflowError(
            f"run is {run.status.value}; only COMPLETED runs can be accepted"
        )
    run.status = RunStatus.ACCEPTED
    run.decided_by = actor.strip()
    run.decided_at = utcnow()
    await audit.record_event(
        session,
        event_type="RUN_ACCEPTED",
        entity_type="agent_run",
        entity_id=run.id,
        actor=run.decided_by,
        payload=_run_event_payload(run),
    )

    await _unlock_next_agent(session, run, actor.strip())
    story = await _get_story(session, run.story_id)
    await recompute_gate_readiness(session, story, actor.strip())
    return run


async def _unlock_next_agent(
    session: AsyncSession, accepted: AgentRun, actor: str
) -> None:
    phase_agents = agents_for_phase(accepted.phase)
    following = sorted(
        (a for a in phase_agents if a.sequence > accepted.sequence),
        key=lambda a: a.sequence,
    )
    # Unlock the next *active* agent, stepping over any that are SKIPPED.
    for agent in following:
        nxt = await latest_run(session, accepted.story_id, agent.key)
        if nxt is None or nxt.status == RunStatus.SKIPPED:
            continue
        if nxt.status == RunStatus.PROPOSED:
            nxt.status = RunStatus.AWAITING_APPROVAL
            await audit.record_event(
                session,
                event_type="RUN_UNLOCKED",
                entity_type="agent_run",
                entity_id=nxt.id,
                actor=actor,
                payload=_run_event_payload(nxt),
            )
        return


async def reject_run(
    session: AsyncSession, run_id: str, actor: str, reason: str
) -> AgentRun:
    if not actor or not actor.strip():
        raise WorkflowError("actor name is required")
    if not reason or not reason.strip():
        raise WorkflowError("a rejection reason is required")
    run = await _get_run(session, run_id)
    if run.status != RunStatus.COMPLETED:
        raise WorkflowError(
            f"run is {run.status.value}; only COMPLETED runs can be rejected"
        )
    run.status = RunStatus.REJECTED
    run.decided_by = actor.strip()
    run.decision_reason = reason.strip()
    run.decided_at = utcnow()
    await audit.record_event(
        session,
        event_type="RUN_REJECTED",
        entity_type="agent_run",
        entity_id=run.id,
        actor=run.decided_by,
        payload={**_run_event_payload(run), "reason": run.decision_reason},
    )
    return run


async def request_rerun(
    session: AsyncSession, run_id: str, actor: str, guidance: str
) -> AgentRun:
    """Create a new attempt with guidance injected into the agent's next
    prompt. The new run still requires its own explicit Approve & Run."""
    if not actor or not actor.strip():
        raise WorkflowError("actor name is required")
    if not guidance or not guidance.strip():
        raise WorkflowError("re-run guidance is required")
    run = await _get_run(session, run_id)
    if run.status not in (RunStatus.COMPLETED, RunStatus.REJECTED, RunStatus.FAILED):
        raise WorkflowError(
            f"run is {run.status.value}; re-run requires COMPLETED, REJECTED or FAILED"
        )
    if run.status == RunStatus.COMPLETED:
        run.status = RunStatus.RERUN_REQUESTED
        run.decided_by = actor.strip()
        run.decided_at = utcnow()

    child = AgentRun(
        story_id=run.story_id,
        agent_key=run.agent_key,
        phase=run.phase,
        sequence=run.sequence,
        attempt=run.attempt + 1,
        status=RunStatus.AWAITING_APPROVAL,
        prompt_version=run.prompt_version,
        guidance=guidance.strip(),
        parent_run_id=run.id,
    )
    session.add(child)
    await session.flush()
    await audit.record_event(
        session,
        event_type="RUN_RERUN_REQUESTED",
        entity_type="agent_run",
        entity_id=run.id,
        actor=actor.strip(),
        payload={
            **_run_event_payload(run),
            "guidance": guidance.strip(),
            "new_run_id": child.id,
        },
    )
    await audit.record_event(
        session,
        event_type="RUN_PROPOSED",
        entity_type="agent_run",
        entity_id=child.id,
        actor=actor.strip(),
        payload={**_run_event_payload(child), "parent_run_id": run.id},
    )
    return child


# ------------------------------------------------------------ gate machine


async def _get_gate(session: AsyncSession, gate_id: str) -> Gate:
    gate = await session.get(Gate, gate_id)
    if gate is None:
        raise NotFoundError(f"gate {gate_id} not found")
    return gate


async def gate_for_phase(session: AsyncSession, story_id: str, phase: Phase) -> Gate:
    gate = (
        await session.execute(
            select(Gate).where(Gate.story_id == story_id, Gate.phase == phase)
        )
    ).scalar_one_or_none()
    if gate is None:
        raise NotFoundError(f"gate for {phase.value} not found on story {story_id}")
    return gate


async def _phase_acceptance_state(
    session: AsyncSession, story: Story, phase: Phase
) -> tuple[bool, list[dict], list[str]]:
    """Returns (all_accepted_and_unblocked, evidence, blockers)."""
    evidence: list[dict] = []
    blockers: list[str] = []
    all_accepted = True
    for agent in agents_for_phase(phase):
        run = await latest_run(session, story.id, agent.key)
        if run is not None and run.status == RunStatus.SKIPPED:
            evidence.append({"agent_key": agent.key, "run_id": run.id, "status": "SKIPPED"})
            continue
        if run is None or run.status != RunStatus.ACCEPTED:
            all_accepted = False
            continue
        blocking = bool((run.output_json or {}).get("release_blocking"))
        if blocking:
            # FCA-scenario / Financial Data Integrity failures: hard-blocking,
            # no override flag exists anywhere in the API.
            blockers.append(
                f"{agent.name}: accepted output contains release-blocking findings"
            )
        evidence.append(
            {
                "agent_key": agent.key,
                "run_id": run.id,
                "attempt": run.attempt,
                "output_hash": run.output_hash,
                "accepted_by": run.decided_by,
                "approved_by": run.approved_by,
            }
        )
    return all_accepted and not blockers, evidence, blockers


async def recompute_gate_readiness(
    session: AsyncSession, story: Story, actor: str = "system"
) -> Gate:
    """Move the current phase's gate to READY_FOR_SIGNOFF when (and only
    when) all phase agents' latest runs are ACCEPTED with no blocking
    findings. Called after every accept; also re-evaluated after re-runs."""
    gate = await gate_for_phase(session, story.id, story.current_phase)
    if gate.status == GateStatus.SIGNED_OFF:
        return gate

    ready, _evidence, blockers = await _phase_acceptance_state(
        session, story, story.current_phase
    )
    if ready and gate.status in (GateStatus.LOCKED, GateStatus.REJECTED):
        gate.status = GateStatus.READY_FOR_SIGNOFF
        await audit.record_event(
            session,
            event_type="GATE_READY",
            entity_type="gate",
            entity_id=gate.id,
            actor=actor,
            payload={
                "story_id": story.id,
                "phase": gate.phase.value,
                "status": gate.status.value,
            },
        )
    elif blockers:
        await audit.record_event(
            session,
            event_type="GATE_BLOCKED",
            entity_type="gate",
            entity_id=gate.id,
            actor="system",
            payload={
                "story_id": story.id,
                "phase": gate.phase.value,
                "blockers": blockers,
            },
        )
    return gate


async def signoff_gate(
    session: AsyncSession,
    gate_id: str,
    approver_name: str,
    approver_role: str,
    rationale: str,
) -> Gate:
    """Formal gate sign-off: named approver, role and typed rationale are all
    mandatory and recorded immutably. Advances the story exactly one phase."""
    for label, value in (
        ("approver name", approver_name),
        ("approver role", approver_role),
        ("decision rationale", rationale),
    ):
        if not value or not value.strip():
            raise WorkflowError(f"{label} is required for gate sign-off")

    gate = await _get_gate(session, gate_id)
    if gate.status != GateStatus.READY_FOR_SIGNOFF:
        raise WorkflowError(
            f"gate is {gate.status.value}; only READY_FOR_SIGNOFF gates can be signed off"
        )
    story = await _get_story(session, gate.story_id)
    if gate.phase != story.current_phase:
        raise WorkflowError("gate phase does not match the story's current phase")

    # Re-verify at the moment of sign-off — never trust a stale READY status.
    ready, evidence, blockers = await _phase_acceptance_state(
        session, story, gate.phase
    )
    if not ready:
        raise WorkflowError(
            "gate criteria no longer satisfied: " + "; ".join(blockers or ["runs changed"])
        )

    gate.status = GateStatus.SIGNED_OFF
    gate.approver_name = approver_name.strip()
    gate.approver_role = approver_role.strip()
    gate.rationale = rationale.strip()
    gate.evidence = {"accepted_runs": evidence}
    gate.decided_at = utcnow()
    await audit.record_event(
        session,
        event_type="GATE_SIGNED_OFF",
        entity_type="gate",
        entity_id=gate.id,
        actor=gate.approver_name,
        payload={
            "story_id": story.id,
            "phase": gate.phase.value,
            "approver_name": gate.approver_name,
            "approver_role": gate.approver_role,
            "rationale": gate.rationale,
            "evidence": gate.evidence,
        },
    )

    nxt = next_phase(story.current_phase)
    if nxt is not None:
        story.current_phase = nxt
        await audit.record_event(
            session,
            event_type="PHASE_ADVANCED",
            entity_type="story",
            entity_id=story.id,
            actor=gate.approver_name,
            payload={"jira_key": story.jira_key, "new_phase": nxt.value},
        )
        await propose_phase_runs(session, story, nxt, actor=gate.approver_name)
    else:
        story.released = True
        await audit.record_event(
            session,
            event_type="STORY_RELEASED",
            entity_type="story",
            entity_id=story.id,
            actor=gate.approver_name,
            payload={"jira_key": story.jira_key},
        )
    return gate


async def reject_gate(
    session: AsyncSession,
    gate_id: str,
    approver_name: str,
    approver_role: str,
    rationale: str,
) -> Gate:
    for label, value in (
        ("approver name", approver_name),
        ("approver role", approver_role),
        ("decision rationale", rationale),
    ):
        if not value or not value.strip():
            raise WorkflowError(f"{label} is required for gate rejection")
    gate = await _get_gate(session, gate_id)
    if gate.status != GateStatus.READY_FOR_SIGNOFF:
        raise WorkflowError(
            f"gate is {gate.status.value}; only READY_FOR_SIGNOFF gates can be rejected"
        )
    gate.status = GateStatus.REJECTED
    gate.approver_name = approver_name.strip()
    gate.approver_role = approver_role.strip()
    gate.rationale = rationale.strip()
    gate.decided_at = utcnow()
    await audit.record_event(
        session,
        event_type="GATE_REJECTED",
        entity_type="gate",
        entity_id=gate.id,
        actor=gate.approver_name,
        payload={
            "story_id": gate.story_id,
            "phase": gate.phase.value,
            "approver_name": gate.approver_name,
            "approver_role": gate.approver_role,
            "rationale": gate.rationale,
        },
    )
    return gate
