"""Stakeholder reporting — a report serves one decision, not one audience.

Four cuts over one shared vocabulary (same severity scale, health bands,
confidence, trust):

- EXEC MI pack (per release, SEALED): board-ready Consumer-Duty-style MI —
  Release Confidence Index, quality-debt position, regulatory evidence
  completeness, an AI-governance line, and honest DORA-adjacent flow metrics.
  Sealed via ReportSnapshot: canonical hash recorded in the audit chain.
- FLOW (live, PM/PO): where work is stuck — gate cycle times, HITL queue
  depth and decision latency, blocking-question aging.
- QUALITY (live, BA/QA): is quality proven — traceability integrity, test
  pyramid, first-time-right per agent, flake index.
- WORKLIST (live, Dev): what do I fix — findings with severity + agent,
  strongest first.

All deterministic reads over persisted runs/gates/registers — no model calls.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime

from ..models import (
    AgentRun,
    Gate,
    Phase,
    Release,
    ReportSnapshot,
    RunStatus,
    ScopeStatus,
    Story,
)
from ..util import canonical_json, sha256_hex, utcnow
from . import audit, flaky_intel, referee, risk_register
from .agents.output_schemas import severity_rank
from .agents.registry import AGENTS

# Default SLA thresholds (days a HITL item may wait before it's a breach),
# overridable per phase via Settings > sla. Release is stricter — it's the
# last checkpoint before a regulated release ships.
DEFAULT_SLA_DAYS: dict[str, float] = {
    "REFINEMENT": 2.0, "DEVELOPMENT": 2.0, "TESTING": 2.0, "RELEASE": 1.0,
}


class ReportingError(Exception):
    pass


def _naive(dt):
    """SQLite round-trips naive datetimes; utcnow() is aware — normalise."""
    return dt.replace(tzinfo=None) if dt is not None else None


def _days_between(a, b) -> float:
    return (_naive(a) - _naive(b)).total_seconds() / 86400


# ------------------------------------------------------------------ helpers


async def _stories(session: AsyncSession, ids: list[str]) -> list[Story]:
    if not ids:
        return []
    rows = (
        await session.execute(select(Story).where(Story.id.in_(ids)))
    ).scalars().all()
    return sorted(rows, key=lambda s: s.jira_key)


async def _latest_runs_all(session: AsyncSession) -> list[AgentRun]:
    return list((await session.execute(select(AgentRun))).scalars().all())


def _latest_per_story_agent(runs: list[AgentRun]) -> dict[tuple[str, str], AgentRun]:
    latest: dict[tuple[str, str], AgentRun] = {}
    for r in runs:
        key = (r.story_id, r.agent_key)
        cur = latest.get(key)
        if cur is None or r.attempt > cur.attempt:
            latest[key] = r
    return latest


# ------------------------------------------------------------- exec MI pack


async def exec_mi_pack(session: AsyncSession, release: Release) -> dict:
    """The live (unsealed) MI pack for a release — seal_mi_pack freezes it."""
    stories = await _stories(session, release.story_ids or [])
    all_runs = await _latest_runs_all(session)
    story_runs = [r for r in all_runs if r.story_id in set(release.story_ids or [])]
    latest = _latest_per_story_agent(story_runs)

    # Per-story health via the Referee (confidence-weighted, blocker-aware).
    story_rows, scores = [], []
    for s in stories:
        health = await referee.assess(session, s.id)
        if health["score"] is not None:
            scores.append(health["score"])
        story_rows.append({
            "jira_key": s.jira_key,
            "summary": s.summary[:100],
            "phase": s.current_phase.value,
            "released": s.released,
            "score": health["score"],
            "band": health["band"],
            "blockers": len(health["blockers"]),
            "inconsistencies": health["inconsistency_count"],
        })
    confidence_index = round(sum(scores) / len(scores)) if scores else None
    bands = {b: sum(1 for r in story_rows if r["band"] == b)
             for b in ("HEALTHY", "AT_RISK", "CRITICAL", "BLOCKED", "NO_DATA")}

    # Quality-debt position (risk register, scoped to the release's stories).
    debt_open = debt_overdue = 0
    debt_by_sev: dict[str, int] = {}
    for s in stories:
        reg = await risk_register.list_register(session, s.id)
        debt_open += reg["summary"]["open"]
        debt_overdue += reg["summary"]["overdue"]
        for sev, n in reg["summary"]["by_severity"].items():
            debt_by_sev[sev] = debt_by_sev.get(sev, 0) + n

    # Regulatory evidence completeness.
    fca_unexecuted = fin_failed = fin_checks = 0
    fca_ok_stories = 0
    for s in stories:
        te = latest.get((s.id, "test_execution_analyst"))
        fdi = latest.get((s.id, "financial_data_integrity"))
        te_o = (te.output_json or {}) if te else {}
        fdi_o = (fdi.output_json or {}) if fdi else {}
        unex = len(te_o.get("unexecuted_fca_scenarios") or [])
        fca_unexecuted += unex
        checks = fdi_o.get("checks") or []
        fin_checks += len(checks)
        fin_failed += sum(1 for c in checks if isinstance(c, dict) and not c.get("passed"))
        if te and not unex and not te_o.get("release_blocking"):
            fca_ok_stories += 1

    # AI-governance line: how governed was the automation, measurably.
    executed = [r for r in story_runs if r.status in (
        RunStatus.COMPLETED, RunStatus.ACCEPTED, RunStatus.REJECTED,
        RunStatus.RERUN_REQUESTED,
    )]
    decided = [r for r in executed if r.status in (
        RunStatus.ACCEPTED, RunStatus.REJECTED, RunStatus.RERUN_REQUESTED,
    )]
    overridden = [r for r in decided if r.status != RunStatus.ACCEPTED]
    accepted = [r for r in decided if r.status == RunStatus.ACCEPTED]
    first_time_right = (
        round(sum(1 for r in accepted if r.attempt == 1) / len(accepted), 3)
        if accepted else None
    )

    # Flow: lead time (first run proposed -> release gate signed) per story.
    lead_days = []
    for s in stories:
        s_runs = [r for r in story_runs if r.story_id == s.id]
        gates = (
            await session.execute(select(Gate).where(
                Gate.story_id == s.id, Gate.phase == Phase.RELEASE
            ))
        ).scalars().all()
        signed = next((g for g in gates if g.decided_at), None)
        if s_runs and signed:
            start = min(r.created_at for r in s_runs)
            lead_days.append(_days_between(signed.decided_at, start))
    rework_stories = len({r.story_id for r in story_runs if r.attempt > 1})

    return {
        "kind": "EXEC_MI",
        "release": {
            "id": release.id, "name": release.name,
            "target_date": release.target_date, "status": release.status,
            "stories": len(stories),
        },
        "generated_at": utcnow().isoformat(),
        "confidence_index": confidence_index,
        "bands": bands,
        "stories": story_rows,
        "quality_debt": {
            "open": debt_open, "overdue": debt_overdue, "by_severity": debt_by_sev,
        },
        "regulatory_evidence": {
            "stories_with_fca_evidence_complete": fca_ok_stories,
            "fca_scenarios_unexecuted": fca_unexecuted,
            "financial_checks": fin_checks,
            "financial_checks_failed": fin_failed,
        },
        "ai_governance": {
            "runs_executed": len(executed),
            "human_decided_pct": round(len(decided) / len(executed), 3) if executed else None,
            "override_rate": round(len(overridden) / len(decided), 3) if decided else None,
            "first_time_right_rate": first_time_right,
        },
        "flow": {
            "stories_released": sum(1 for s in stories if s.released),
            "avg_lead_time_days": round(sum(lead_days) / len(lead_days), 1) if lead_days else None,
            # Honest label: we measure REWORK (re-run attempts), not post-release
            # failure — the Escape Loop (roadmap) would upgrade this to true CFR.
            "rework_story_rate": round(rework_stories / len(stories), 3) if stories else None,
        },
    }


async def seal_mi_pack(session: AsyncSession, release: Release, actor: str) -> dict:
    """Freeze the MI pack: persist + canonical hash + audit-chain event."""
    pack = await exec_mi_pack(session, release)
    payload_hash = sha256_hex(canonical_json(pack))
    snap = ReportSnapshot(
        release_id=release.id, kind="EXEC_MI",
        payload=pack, payload_hash=payload_hash, generated_by=actor,
    )
    session.add(snap)
    await session.flush()
    await audit.record_event(
        session, event_type="REPORT_SEALED", entity_type="report_snapshot",
        entity_id=snap.id, actor=actor,
        payload={
            "release": release.name, "kind": "EXEC_MI",
            "payload_hash": payload_hash,
            "confidence_index": pack["confidence_index"],
            "quality_debt_open": pack["quality_debt"]["open"],
        },
    )
    return {
        "snapshot_id": snap.id, "release": release.name,
        "payload_hash": payload_hash, "generated_by": actor,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


# ------------------------------------------------------------------- flow


async def _hitl_queue_items(session: AsyncSession):
    """Runs/gates currently waiting on a human, with phase + age attached.
    Shared by Flow (the full queue) and the SLA breach report (the
    over-threshold subset) so both read the same underlying wait times."""
    runs = await _latest_runs_all(session)
    gates = list((await session.execute(select(Gate))).scalars().all())
    stories = {
        s.id: s for s in (await session.execute(select(Story))).scalars().all()
    }
    now = utcnow()

    def _age_days(dt) -> float:
        return round(_days_between(now, dt), 1) if dt else 0.0

    awaiting = [
        {
            "kind": "RUN_APPROVAL" if r.status == RunStatus.AWAITING_APPROVAL else "RUN_DECISION",
            "jira_key": stories[r.story_id].jira_key if r.story_id in stories else "?",
            "agent": AGENTS[r.agent_key].name if r.agent_key in AGENTS else r.agent_key,
            "phase": r.phase.value,
            "age_days": _age_days(r.created_at if r.status == RunStatus.AWAITING_APPROVAL else r.completed_at),
        }
        for r in runs
        if r.status in (RunStatus.AWAITING_APPROVAL, RunStatus.COMPLETED)
    ]
    awaiting.sort(key=lambda x: -x["age_days"])
    ready_gates = [
        {"jira_key": stories[g.story_id].jira_key if g.story_id in stories else "?",
         "phase": g.phase.value, "age_days": _age_days(g.created_at)}
        for g in gates if g.status.value == "READY_FOR_SIGNOFF"
    ]
    return awaiting, ready_gates, runs, gates, stories, now


async def flow_report(session: AsyncSession) -> dict:
    """PM/PO cut: where is work stuck, who owes what."""
    awaiting, ready_gates, runs, gates, stories, now = await _hitl_queue_items(session)

    # Gate cycle time per phase (created -> decided).
    cycle: dict[str, list[float]] = {}
    for g in gates:
        if g.decided_at and g.created_at:
            cycle.setdefault(g.phase.value, []).append(
                _days_between(g.decided_at, g.created_at)
            )
    gate_cycle = [
        {"phase": p, "avg_days": round(sum(v) / len(v), 1), "gates": len(v)}
        for p, v in cycle.items()
    ]

    # Decision latency: completed -> decided, per role-relevant measure.
    latencies = [
        _days_between(r.decided_at, r.completed_at)
        for r in runs
        if r.decided_at and r.completed_at
    ]

    # Blocking-question aging (Three Amigos, blocking=true, story still pre-BDD).
    blocking_qs = []
    latest = _latest_per_story_agent(runs)
    for (sid, agent_key), r in latest.items():
        if agent_key != "three_amigos" or not r.output_json:
            continue
        for q in r.output_json.get("open_questions") or []:
            if isinstance(q, dict) and q.get("blocking"):
                blocking_qs.append({
                    "jira_key": stories[sid].jira_key if sid in stories else "?",
                    "question": str(q.get("question"))[:140],
                    "owner": q.get("owner_persona"),
                    "age_days": round(_days_between(now, r.completed_at), 1) if r.completed_at else 0.0,
                })

    return {
        "generated_at": now.isoformat(),
        "gate_cycle_times": gate_cycle,
        "hitl_queue": {
            "depth": len(awaiting) + len(ready_gates),
            "runs": awaiting[:20],
            "gates_ready": ready_gates,
            "avg_decision_latency_days": round(sum(latencies) / len(latencies), 2)
            if latencies else None,
        },
        "blocking_questions": blocking_qs,
    }


# ------------------------------------------------------------- sla breaches


async def sla_breach_report(session: AsyncSession, thresholds: dict | None = None) -> dict:
    """PM cut: HITL items past their phase's SLA threshold — the standup
    escalation list, not the full queue. Thresholds are configurable per
    phase (Settings > sla); unset phases fall back to DEFAULT_SLA_DAYS."""
    th = {**DEFAULT_SLA_DAYS, **(thresholds or {})}
    awaiting, ready_gates, *_ = await _hitl_queue_items(session)

    breaches = []
    for item in awaiting:
        limit = th.get(item["phase"], DEFAULT_SLA_DAYS.get(item["phase"], 2.0))
        if item["age_days"] > limit:
            breaches.append({
                **item, "threshold_days": limit,
                "over_by_days": round(item["age_days"] - limit, 1),
            })
    for g in ready_gates:
        limit = th.get(g["phase"], DEFAULT_SLA_DAYS.get(g["phase"], 2.0))
        if g["age_days"] > limit:
            breaches.append({
                "kind": "GATE_SIGNOFF", "jira_key": g["jira_key"], "agent": None,
                "phase": g["phase"], "age_days": g["age_days"],
                "threshold_days": limit, "over_by_days": round(g["age_days"] - limit, 1),
            })
    breaches.sort(key=lambda x: -x["over_by_days"])

    by_phase: dict[str, int] = {}
    for b in breaches:
        by_phase[b["phase"]] = by_phase.get(b["phase"], 0) + 1

    return {
        "generated_at": utcnow().isoformat(),
        "thresholds": th,
        "breaches": breaches,
        "summary": {"total": len(breaches), "by_phase": by_phase},
    }


# -------------------------------------------------------- release readiness


async def readiness_report(session: AsyncSession) -> dict:
    """PO cut: per-story readiness/scope-risk across all active, unreleased
    stories — live, not scoped to a single release. Decision: what to
    descope now, while there's still time to react, not at the release gate."""
    stories = [
        s for s in (await session.execute(select(Story))).scalars().all()
        if s.scope_status == ScopeStatus.ACTIVE and not s.released
    ]
    releases = list((await session.execute(select(Release))).scalars().all())
    target_date: dict[str, str] = {}
    for rel in releases:
        if not rel.target_date:
            continue
        for sid in rel.story_ids or []:
            if sid not in target_date or rel.target_date < target_date[sid]:
                target_date[sid] = rel.target_date

    now = utcnow()
    rows = []
    for s in stories:
        health = await referee.assess(session, s.id)
        reg = await risk_register.list_register(session, s.id)
        td = target_date.get(s.id)
        days_to_target = None
        if td:
            try:
                days_to_target = round(_days_between(datetime.fromisoformat(td), now), 1)
            except ValueError:
                days_to_target = None

        band = health["band"]
        open_risk = reg["summary"]["open"]
        overdue_risk = reg["summary"]["overdue"]
        if band in ("CRITICAL", "BLOCKED") or overdue_risk:
            scope_risk = "HIGH"
        elif band == "AT_RISK" or open_risk:
            scope_risk = "MEDIUM"
        else:
            scope_risk = "LOW"

        rows.append({
            "jira_key": s.jira_key,
            "summary": s.summary[:100],
            "phase": s.current_phase.value,
            "score": health["score"],
            "band": band,
            "blockers": len(health["blockers"]),
            "open_risks": open_risk,
            "overdue_risks": overdue_risk,
            "target_date": td,
            "days_to_target": days_to_target,
            "scope_risk": scope_risk,
        })

    risk_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows.sort(key=lambda r: (
        risk_rank[r["scope_risk"]],
        r["days_to_target"] if r["days_to_target"] is not None else 9999,
    ))

    return {
        "generated_at": now.isoformat(),
        "stories": rows,
        "summary": {
            "total": len(rows),
            "high_risk": sum(1 for r in rows if r["scope_risk"] == "HIGH"),
            "medium_risk": sum(1 for r in rows if r["scope_risk"] == "MEDIUM"),
        },
    }


# ------------------------------------------------------------ ac ambiguity


async def ac_ambiguity_digest(session: AsyncSession) -> dict:
    """BA/QA cut: unresolved Three Amigos open questions, grouped by story —
    blocking and stories that moved past Refinement while still unresolved
    first. Decision: what to clarify with the PO before dev starts, not
    after — that's the expensive kind of rework."""
    runs = await _latest_runs_all(session)
    stories = {
        s.id: s for s in (await session.execute(select(Story))).scalars().all()
    }
    latest = _latest_per_story_agent(runs)

    rows = []
    for (sid, agent_key), r in latest.items():
        if agent_key != "three_amigos" or not r.output_json:
            continue
        questions = r.output_json.get("open_questions") or []
        if not questions:
            continue
        s = stories.get(sid)
        if s is None:
            continue
        blocking = [q for q in questions if isinstance(q, dict) and q.get("blocking")]
        non_blocking = [q for q in questions if isinstance(q, dict) and not q.get("blocking")]
        escalate = s.current_phase != Phase.REFINEMENT and bool(blocking)
        rows.append({
            "jira_key": s.jira_key,
            "phase": s.current_phase.value,
            "escalate": escalate,
            "blocking": [
                {"question": str(q.get("question"))[:200], "owner": q.get("owner_persona")}
                for q in blocking
            ],
            "non_blocking": [
                {"question": str(q.get("question"))[:200], "owner": q.get("owner_persona")}
                for q in non_blocking
            ],
        })
    rows.sort(key=lambda r: (not r["escalate"], -len(r["blocking"])))

    return {
        "generated_at": utcnow().isoformat(),
        "stories": rows,
        "summary": {
            "stories_with_open_questions": len(rows),
            "stories_blocking": sum(1 for r in rows if r["blocking"]),
            "escalations": sum(1 for r in rows if r["escalate"]),
        },
    }


# ----------------------------------------------------------- override digest


async def override_digest(session: AsyncSession, assignee: str | None = None) -> dict:
    """Dev cut: why agent output on my stories got overridden — rejection
    reasons and re-run guidance, grouped by agent, newest first. Decision:
    how to brief the agent (or fix the underlying code) so the same
    override doesn't repeat next attempt."""
    stories = {
        s.id: s for s in (await session.execute(select(Story))).scalars().all()
    }
    story_ids = (
        {sid for sid, s in stories.items() if s.assignee == assignee}
        if assignee else set(stories.keys())
    )
    runs = [r for r in await _latest_runs_all(session) if r.story_id in story_ids]

    by_agent: dict[str, list[dict]] = {}
    for r in runs:
        jira_key = stories[r.story_id].jira_key if r.story_id in stories else "?"
        if r.status == RunStatus.REJECTED and r.decision_reason:
            by_agent.setdefault(r.agent_key, []).append({
                "jira_key": jira_key, "kind": "REJECTED", "reason": r.decision_reason,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            })
        if r.parent_run_id and r.guidance:
            by_agent.setdefault(r.agent_key, []).append({
                "jira_key": jira_key, "kind": "RERUN_GUIDANCE", "reason": r.guidance,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            })

    agents = []
    for key, items in by_agent.items():
        items.sort(key=lambda x: x["decided_at"] or "", reverse=True)
        agents.append({
            "agent_key": key,
            "agent_name": AGENTS[key].name if key in AGENTS else key,
            "count": len(items),
            "items": items[:10],
        })
    agents.sort(key=lambda a: -a["count"])

    return {
        "generated_at": utcnow().isoformat(),
        "assignee": assignee,
        "agents": agents,
        "summary": {"total_overrides": sum(a["count"] for a in agents)},
    }


# ----------------------------------------------------------------- quality


async def quality_report(session: AsyncSession) -> dict:
    """BA/QA cut: is quality proven, where are the gaps."""
    runs = await _latest_runs_all(session)
    stories = {
        s.id: s for s in (await session.execute(select(Story))).scalars().all()
    }
    latest = _latest_per_story_agent(runs)

    # Traceability integrity from the AC Compliance RTM.
    trace_rows, pyramid = [], {"unit": 0, "api": 0, "ui": 0}
    uncovered_examples = 0
    for (sid, agent_key), r in latest.items():
        o = r.output_json or {}
        if agent_key == "ac_compliance" and o.get("ac_mapping"):
            statuses = [m.get("status") for m in o["ac_mapping"] if isinstance(m, dict)]
            trace_rows.append({
                "jira_key": stories[sid].jira_key if sid in stories else "?",
                "ac_total": len(statuses),
                "covered": statuses.count("COVERED"),
                "partial": statuses.count("PARTIAL"),
                "not_covered": statuses.count("NOT_COVERED"),
            })
        if agent_key == "bdd_generator":
            p = o.get("pyramid") or {}
            for k in pyramid:
                pyramid[k] += int(p.get(k) or 0)
            cov = o.get("coverage") or {}
            uncovered_examples += len(cov.get("uncovered_examples") or [])

    # First-time-right per agent (accepted on attempt 1 / accepted).
    ftr: dict[str, list[int]] = {}
    for r in runs:
        if r.status == RunStatus.ACCEPTED:
            ftr.setdefault(r.agent_key, []).append(1 if r.attempt == 1 else 0)
    first_time_right = sorted(
        (
            {
                "agent_key": k,
                "agent_name": AGENTS[k].name if k in AGENTS else k,
                "accepted": len(v),
                "first_time_right_rate": round(sum(v) / len(v), 2),
            }
            for k, v in ftr.items()
        ),
        key=lambda x: x["first_time_right_rate"],
    )

    flake = await flaky_intel.ledger(session)
    return {
        "generated_at": utcnow().isoformat(),
        "traceability": trace_rows,
        "uncovered_example_cards": uncovered_examples,
        "test_pyramid": pyramid,
        "first_time_right": first_time_right,
        "flake_index": flake["summary"],
    }


# ---------------------------------------------------------------- worklist


async def worklist(session: AsyncSession, story_id: str) -> dict:
    """Dev cut: the findings to fix on this story, strongest first."""
    runs = [
        r for r in await _latest_runs_all(session)
        if r.story_id == story_id
    ]
    latest = _latest_per_story_agent(runs)
    items = []
    for (_, agent_key), r in latest.items():
        o = r.output_json or {}
        for f in o.get("findings") or []:
            if not isinstance(f, dict):
                continue
            items.append({
                "agent_key": agent_key,
                "agent_name": AGENTS[agent_key].name if agent_key in AGENTS else agent_key,
                "phase": r.phase.value,
                "severity": f.get("severity") or "MEDIUM",
                "title": f.get("title") or "",
                "detail": f.get("detail") or "",
                "run_status": r.status.value,
            })
    items.sort(key=lambda i: -severity_rank(i["severity"]))
    return {
        "story_id": story_id,
        "generated_at": utcnow().isoformat(),
        "items": items,
        "counts": {
            s: sum(1 for i in items if i["severity"] == s)
            for s in ("BLOCKER", "CRITICAL", "HIGH", "MEDIUM", "LOW")
            if any(i["severity"] == s for i in items)
        },
    }


# ------------------------------------------------------------- HTML (exec)


def _e(v) -> str:
    return (
        str(v if v is not None else "—")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def render_mi_html(pack: dict, payload_hash: str | None = None) -> str:
    """Print-ready one-page MI pack (Consumer-Duty-style board MI)."""
    r = pack["release"]
    ci = pack["confidence_index"]
    band_cls = "ok" if (ci or 0) >= 80 else "warn" if (ci or 0) >= 55 else "bad"
    story_rows = "".join(
        f"<tr><td><b>{_e(s['jira_key'])}</b></td><td>{_e(s['summary'])}</td>"
        f"<td>{_e(s['phase'])}</td><td class='{('ok' if s['band']=='HEALTHY' else 'bad' if s['band'] in ('BLOCKED','CRITICAL') else 'warn')}'>"
        f"{_e(s['score'])} · {_e(s['band'])}</td>"
        f"<td>{_e(s['blockers'])}</td><td>{'Yes' if s['released'] else 'No'}</td></tr>"
        for s in pack["stories"]
    )
    qd, re_, ai, fl = (pack["quality_debt"], pack["regulatory_evidence"],
                       pack["ai_governance"], pack["flow"])
    pct = lambda v: f"{round(v * 100)}%" if v is not None else "—"  # noqa: E731
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>MI Pack — {_e(r['name'])}</title>
<style>
body{{font:13px/1.5 system-ui,Segoe UI,sans-serif;color:#111;max-width:900px;margin:32px auto;padding:0 16px}}
h1{{font-size:20px;margin:0}} h2{{font-size:14px;margin:22px 0 6px;border-bottom:1px solid #ddd;padding-bottom:3px}}
table{{width:100%;border-collapse:collapse;font-size:12px}} th,td{{text-align:left;padding:4px 8px;border-bottom:1px solid #eee}}
th{{color:#666;font-weight:600}} .meta{{color:#666;font-size:11px}}
.big{{font-size:34px;font-weight:800}} .ok{{color:#0a7d33}} .warn{{color:#b07d00}} .bad{{color:#b00020}}
.grid{{display:flex;gap:24px;margin:14px 0}} .cell b{{display:block;font-size:22px}}
.seal{{background:#f4f6f8;border:1px solid #ddd;border-radius:6px;padding:8px 12px;font-size:11px;margin-top:20px}}
@media print{{body{{margin:8px auto}}}}
</style></head><body>
<h1>Release MI Pack — {_e(r['name'])}</h1>
<p class="meta">Target {_e(r['target_date'])} · {_e(r['stories'])} stories ·
generated {_e(pack['generated_at'])} · AI Agentic QE Platform</p>

<div class="grid">
  <div class="cell"><span class="big {band_cls}">{_e(ci)}</span><br>Release Confidence Index</div>
  <div class="cell"><b class="{'bad' if qd['overdue'] else 'warn' if qd['open'] else 'ok'}">{qd['open']}</b>Open accepted risks ({qd['overdue']} overdue)</div>
  <div class="cell"><b class="{'bad' if re_['fca_scenarios_unexecuted'] else 'ok'}">{re_['fca_scenarios_unexecuted']}</b>FCA scenarios unexecuted</div>
  <div class="cell"><b>{_e(pct(ai['human_decided_pct']))}</b>Runs human-decided</div>
</div>

<h2>1 · Story health (Cross-Agent Referee)</h2>
<table><thead><tr><th>Story</th><th>Summary</th><th>Phase</th><th>Health</th><th>Blockers</th><th>Released</th></tr></thead>
<tbody>{story_rows}</tbody></table>

<h2>2 · Quality-debt position (Risk Acceptance Register)</h2>
<p>{qd['open']} open ({_e(qd['by_severity'])}), {qd['overdue']} overdue for review.</p>

<h2>3 · Regulatory evidence</h2>
<p>{re_['stories_with_fca_evidence_complete']} of {r['stories']} stories with complete FCA
scenario evidence · financial checks {re_['financial_checks'] - re_['financial_checks_failed']}/{re_['financial_checks']} reconciled.</p>

<h2>4 · AI governance</h2>
<p>{ai['runs_executed']} agent runs · {_e(pct(ai['human_decided_pct']))} human-decided ·
override rate {_e(pct(ai['override_rate']))} · first-time-right {_e(pct(ai['first_time_right_rate']))}.
Blocking-capable agents cannot be disabled; FCA/financial failures carry no override.</p>

<h2>5 · Flow</h2>
<p>{fl['stories_released']} released · avg lead time {_e(fl['avg_lead_time_days'])} days ·
rework rate {_e(pct(fl['rework_story_rate']))} <span class="meta">(rework = re-run attempts;
true change-failure-rate requires post-release incident data)</span>.</p>

<div class="seal">SEALED SNAPSHOT — canonical hash
<code>{_e(payload_hash or 'unsealed preview')}</code>, recorded in the platform's
append-only audit chain (REPORT_SEALED). These figures are immutable and reproducible.</div>
</body></html>"""
