"""Push TO Jira — always human-approved, never lossy.

Flow: DRAFT (rendered preview shown to the human) -> APPROVED -> SENT,
or FAILED -> RETRYING -> SENT. Failed pushes stay in the queue with their
error; approved posts are never lost. Every attempt writes an audit event.

Gate sign-off pushes are enqueued automatically (per-gate setting) because
the sign-off itself was the human approval.
"""

import base64
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import (
    AgentRun,
    AuditEvent,
    Gate,
    Phase,
    PushQueueItem,
    PushStatus,
    PushType,
    RunStatus,
    Story,
)
from ...util import utcnow_iso
from .. import audit
from ..workflow import NotFoundError, WorkflowError
from . import adf
from .adapter import JiraAdapter


# ---------------------------------------------------------------- helpers


def _push_event_payload(item: PushQueueItem) -> dict:
    return {
        "push_id": item.id,
        "story_id": item.story_id,
        "push_type": item.push_type.value,
        "status": item.status.value,
        "attempts": item.attempts,
        "jira_key": item.payload.get("jira_key"),
    }


async def _record(
    session: AsyncSession, event_type: str, item: PushQueueItem, actor: str, extra: dict | None = None
) -> None:
    await audit.record_event(
        session,
        event_type=event_type,
        entity_type="push",
        entity_id=item.id,
        actor=actor,
        payload={**_push_event_payload(item), **(extra or {})},
    )


async def _create_item(
    session: AsyncSession,
    story: Story,
    push_type: PushType,
    payload: dict,
    actor: str,
) -> PushQueueItem:
    item = PushQueueItem(
        story_id=story.id,
        push_type=push_type,
        payload={"jira_key": story.jira_key, **payload},
    )
    session.add(item)
    await session.flush()
    await _record(session, "PUSH_DRAFTED", item, actor)
    return item


async def _get_item(session: AsyncSession, item_id: str) -> PushQueueItem:
    item = await session.get(PushQueueItem, item_id)
    if item is None:
        raise NotFoundError(f"push item {item_id} not found")
    return item


# ------------------------------------------------------------ draft builders


def _story_link(platform_base_url: str, story: Story) -> str:
    return f"{platform_base_url.rstrip('/')}/stories/{story.id}"


def _build_agent_summary_adf(story: Story, run: AgentRun, link: str) -> tuple[dict, str]:
    output = run.output_json or {}
    agent_name = output.get("agent_name", run.agent_key)
    verdict = output.get("verdict", "N/A")
    summary = output.get("summary", "")
    findings = output.get("findings") or []

    blocks = [
        adf.heading(f"PACT QE — {agent_name}", level=3),
        adf.labelled("Verdict", verdict),
        adf.labelled("Accepted by", run.decided_by or "—"),
        adf.labelled("Run", f"attempt {run.attempt}, model {run.model or 'n/a'}"),
        adf.paragraph(summary),
    ]
    if findings:
        blocks.append(adf.paragraph("Key findings:", bold=True))
        blocks.append(adf.bullet_list([str(f) for f in findings]))
    blocks.append(adf.link_paragraph("View full output in the QE platform", link))

    preview_lines = [
        f"PACT QE — {agent_name}",
        f"Verdict: {verdict}",
        f"Accepted by: {run.decided_by or '—'}",
        summary,
        *[f"- {f}" for f in findings],
        f"Link: {link}",
    ]
    return adf.doc(*blocks), "\n".join(preview_lines)


def _assemble_feature_text(output: dict) -> str:
    """Assemble a complete, commit-ready .feature file from the BDD agent's
    structured output (feature header + narrative + background + tagged
    scenarios). Tolerates the older flat shape and string scenarios."""
    feature = output.get("feature") or {}
    scenarios = output.get("scenarios") or []
    lines: list[str] = []

    name = feature.get("name")
    if name:
        lines.append(f"Feature: {name}")
        narrative = feature.get("narrative") or {}
        if narrative.get("as_a"):
            lines.append(f"  As a {narrative['as_a']}")
        if narrative.get("i_want"):
            lines.append(f"  I want {narrative['i_want']}")
        if narrative.get("so_that"):
            lines.append(f"  So that {narrative['so_that']}")
        lines.append("")

    background = feature.get("background") or []
    if background:
        lines.append("  Background:")
        for step in background:
            lines.append(f"    {step}")
        lines.append("")

    for sc in scenarios:
        if isinstance(sc, dict):
            tags = sc.get("tags") or []
            if tags:
                lines.append("  " + " ".join(tags))
            for gl in (sc.get("gherkin") or "").splitlines():
                lines.append(f"  {gl}" if gl.strip() else gl)
            lines.append("")
        elif isinstance(sc, str):
            lines.extend(f"  {line}" for line in sc.splitlines())
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_bdd_adf(story: Story, run: AgentRun, link: str) -> tuple[dict, str]:
    output = run.output_json or {}
    scenarios = output.get("scenarios") or []
    blocks = [adf.heading(f"Approved BDD feature — {story.jira_key}", level=3)]
    preview_lines = [f"Approved BDD feature — {story.jira_key}"]

    coverage = output.get("coverage") or {}
    if coverage:
        cov_line = (
            f"{coverage.get('rules_covered', '?')}/{coverage.get('rules_total', '?')} "
            f"rules covered · {coverage.get('ac_covered', '?')} AC"
        )
        blocks.append(adf.labelled("Coverage", cov_line))
        preview_lines.append(f"Coverage: {cov_line}")

    if scenarios:
        feature_text = _assemble_feature_text(output)
        blocks.append(adf.code_block(feature_text, language="gherkin"))
        preview_lines.append(feature_text)
    else:
        summary = output.get("summary", "No scenarios present on this run.")
        blocks.append(adf.paragraph(summary))
        preview_lines.append(summary)

    blocks.append(adf.link_paragraph("View in the QE platform", link))
    preview_lines.append(f"Link: {link}")
    return adf.doc(*blocks), "\n".join(preview_lines)


def _build_gate_signoff_adf(story: Story, gate: Gate, link: str) -> tuple[dict, str]:
    gate_no = list(Phase).index(gate.phase) + 1
    title = f"QE Gate {gate_no} Sign-Off — {gate.phase.value.title()}"
    decided = gate.decided_at.isoformat() if gate.decided_at else utcnow_iso()
    blocks = [
        adf.heading(title, level=3),
        adf.labelled("Approver", f"{gate.approver_name} ({gate.approver_role})"),
        adf.labelled("Timestamp", decided),
        adf.labelled("Rationale", gate.rationale or ""),
        adf.link_paragraph("Evidence & audit trail in the QE platform", link),
    ]
    preview = "\n".join(
        [
            title,
            f"Approver: {gate.approver_name} ({gate.approver_role})",
            f"Timestamp: {decided}",
            f"Rationale: {gate.rationale}",
            f"Link: {link}",
        ]
    )
    return adf.doc(*blocks), preview


async def draft_agent_summary(
    session: AsyncSession, run_id: str, actor: str, platform_base_url: str
) -> PushQueueItem:
    """'Post summary to Jira' — offered after a human Accepts an agent run."""
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"agent run {run_id} not found")
    if run.status != RunStatus.ACCEPTED:
        raise WorkflowError("only ACCEPTED runs can be posted to Jira")
    story = await session.get(Story, run.story_id)
    link = _story_link(platform_base_url, story)
    adf_body, preview = _build_agent_summary_adf(story, run, link)
    return await _create_item(
        session,
        story,
        PushType.COMMENT,
        {"kind": "agent_summary", "run_id": run.id, "adf": adf_body, "preview_text": preview},
        actor,
    )


async def draft_bdd_scenarios(
    session: AsyncSession, run_id: str, actor: str, platform_base_url: str
) -> PushQueueItem:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise NotFoundError(f"agent run {run_id} not found")
    if run.status != RunStatus.ACCEPTED:
        raise WorkflowError("only ACCEPTED runs can be posted to Jira")
    story = await session.get(Story, run.story_id)
    link = _story_link(platform_base_url, story)
    adf_body, preview = _build_bdd_adf(story, run, link)
    return await _create_item(
        session,
        story,
        PushType.COMMENT,
        {"kind": "bdd_scenarios", "run_id": run.id, "adf": adf_body, "preview_text": preview},
        actor,
    )


# ------------------------------------------------------------------ sending


async def _send(session: AsyncSession, adapter: JiraAdapter, item: PushQueueItem, actor: str) -> PushQueueItem:
    key = item.payload["jira_key"]
    item.attempts += 1
    try:
        if item.push_type == PushType.COMMENT:
            await adapter.add_comment(key, item.payload["adf"])
        elif item.push_type == PushType.LABEL:
            await adapter.add_label(key, item.payload["label"])
        elif item.push_type == PushType.TRANSITION:
            wanted = item.payload["transition_name"].strip().lower()
            transitions = await adapter.get_transitions(key)
            match = next(
                (t for t in transitions if t["name"].strip().lower() == wanted), None
            )
            if match is None:
                available = ", ".join(t["name"] for t in transitions) or "none"
                raise WorkflowError(
                    f"transition '{item.payload['transition_name']}' not available "
                    f"on {key} (available: {available})"
                )
            item.payload = {**item.payload, "resolved_transition_id": match["id"]}
            await adapter.transition_issue(key, match["id"])
        elif item.push_type == PushType.ATTACHMENT:
            content = base64.b64decode(item.payload["content_b64"])
            await adapter.attach_file(key, item.payload["filename"], content)
        else:  # pragma: no cover
            raise WorkflowError(f"unknown push type {item.push_type}")
    except Exception as exc:
        item.status = PushStatus.FAILED
        item.last_error = str(exc)[:1000]
        await _record(session, "PUSH_FAILED", item, actor, {"error": item.last_error})
        return item

    item.status = PushStatus.SENT
    item.last_error = None
    await _record(session, "PUSH_SENT", item, actor)
    return item


async def approve_and_send(
    session: AsyncSession, adapter: JiraAdapter, item_id: str, actor: str
) -> PushQueueItem:
    """Human approved the previewed push — send it."""
    if not actor or not actor.strip():
        raise WorkflowError("actor name is required")
    item = await _get_item(session, item_id)
    if item.status != PushStatus.DRAFT:
        raise WorkflowError(f"push is {item.status.value}; only DRAFT pushes can be approved")
    item.status = PushStatus.APPROVED
    item.approved_by = actor.strip()
    await _record(session, "PUSH_APPROVED", item, actor.strip())
    return await _send(session, adapter, item, actor.strip())


async def retry(
    session: AsyncSession, adapter: JiraAdapter, item_id: str, actor: str
) -> PushQueueItem:
    if not actor or not actor.strip():
        raise WorkflowError("actor name is required")
    item = await _get_item(session, item_id)
    if item.status != PushStatus.FAILED:
        raise WorkflowError(f"push is {item.status.value}; only FAILED pushes can be retried")
    item.status = PushStatus.RETRYING
    await _record(session, "PUSH_RETRIED", item, actor.strip())
    return await _send(session, adapter, item, actor.strip())


# --------------------------------------------------- gate sign-off pushes


async def build_release_audit_pack(session: AsyncSession, story: Story) -> dict:
    """The immutable release audit pack: who approved what, when, with what
    evidence — plus a chain-integrity verdict at time of generation."""
    gates = (
        (await session.execute(select(Gate).where(Gate.story_id == story.id)))
        .scalars()
        .all()
    )
    runs = (
        (await session.execute(select(AgentRun).where(AgentRun.story_id == story.id)))
        .scalars()
        .all()
    )
    entity_ids = [story.id, *[g.id for g in gates], *[r.id for r in runs]]
    events = (
        (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id.in_(entity_ids))
                .order_by(AuditEvent.id)
            )
        )
        .scalars()
        .all()
    )
    chain = await audit.verify_chain(session)
    return {
        "generated_at": utcnow_iso(),
        "story": {
            "jira_key": story.jira_key,
            "summary": story.summary,
            "fca_impact": story.fca_impact.value if story.fca_impact else None,
            "cloud": story.cloud.value if story.cloud else None,
            "released": story.released,
        },
        "gates": [
            {
                "phase": g.phase.value,
                "status": g.status.value,
                "approver_name": g.approver_name,
                "approver_role": g.approver_role,
                "rationale": g.rationale,
                "decided_at": g.decided_at.isoformat() if g.decided_at else None,
                "evidence": g.evidence,
            }
            for g in gates
        ],
        "agent_runs": [
            {
                "agent_key": r.agent_key,
                "attempt": r.attempt,
                "status": r.status.value,
                "approved_by": r.approved_by,
                "decided_by": r.decided_by,
                "model": r.model,
                "prompt_version": r.prompt_version,
                "input_hash": r.input_hash,
                "output_hash": r.output_hash,
            }
            for r in runs
        ],
        "audit_events": [
            {
                "id": e.id,
                "created_at": e.created_at,
                "event_type": e.event_type,
                "actor": e.actor,
                "payload": e.payload,
                "event_hash": e.event_hash,
            }
            for e in events
        ],
        "audit_chain_verification": chain,
    }


async def handle_gate_signoff(
    session: AsyncSession,
    adapter: JiraAdapter,
    story: Story,
    gate: Gate,
    app_settings: dict,
    actor: str,
) -> list[PushQueueItem]:
    """Enqueue and send the per-gate pushes. Auto-approved: the sign-off
    itself was the recorded human approval. Each toggle is a per-gate setting."""
    gate_cfg = (app_settings.get("gates") or {}).get(gate.phase.value, {})
    platform_url = (app_settings.get("platform") or {}).get(
        "base_url", "http://localhost:5173"
    )
    link = _story_link(platform_url, story)
    items: list[PushQueueItem] = []

    async def _auto_send(item: PushQueueItem) -> None:
        item.status = PushStatus.APPROVED
        item.approved_by = actor
        await _record(
            session, "PUSH_APPROVED", item, actor, {"auto": True, "gate_id": gate.id}
        )
        await _send(session, adapter, item, actor)
        items.append(item)

    if gate_cfg.get("auto_post_comment"):
        adf_body, preview = _build_gate_signoff_adf(story, gate, link)
        item = await _create_item(
            session,
            story,
            PushType.COMMENT,
            {"kind": "gate_signoff", "gate_id": gate.id, "adf": adf_body, "preview_text": preview},
            actor,
        )
        await _auto_send(item)

    if gate_cfg.get("apply_label") and gate_cfg.get("label"):
        item = await _create_item(
            session,
            story,
            PushType.LABEL,
            {
                "kind": "gate_label",
                "gate_id": gate.id,
                "label": gate_cfg["label"],
                "preview_text": f"Apply label '{gate_cfg['label']}' to {story.jira_key}",
            },
            actor,
        )
        await _auto_send(item)

    if gate_cfg.get("transition_name"):
        item = await _create_item(
            session,
            story,
            PushType.TRANSITION,
            {
                "kind": "gate_transition",
                "gate_id": gate.id,
                "transition_name": gate_cfg["transition_name"],
                "preview_text": (
                    f"Transition {story.jira_key} to '{gate_cfg['transition_name']}'"
                ),
            },
            actor,
        )
        await _auto_send(item)

    if gate.phase == Phase.RELEASE and gate_cfg.get("attach_evidence"):
        pack = await build_release_audit_pack(session, story)
        content = json.dumps(pack, indent=2, default=str).encode("utf-8")
        item = await _create_item(
            session,
            story,
            PushType.ATTACHMENT,
            {
                "kind": "release_audit_pack",
                "gate_id": gate.id,
                "filename": f"{story.jira_key}-release-audit-pack.json",
                "content_b64": base64.b64encode(content).decode("ascii"),
                "preview_text": (
                    f"Attach release audit pack ({len(content)} bytes) to {story.jira_key}"
                ),
            },
            actor,
        )
        await _auto_send(item)

    return items
