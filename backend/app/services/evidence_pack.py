"""One-click Regulatory Evidence Pack.

Assembles a story's full compliance record — gate sign-offs, the AI-governance
execution record (every agent run with prompt version, model, tokens and output
hash), the regulatory & financial evidence, the Release Health synthesis, and the
verified hash-chain — and renders it as a self-contained, printable HTML document
an FCA auditor can read (or print to PDF) with one click.

Reuses build_release_audit_pack (the immutable pack) for gates / hashes / chain,
and enriches it with the human-readable results the auditor actually wants.
"""

import html

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentRun, RunStatus, Story
from . import referee
from .agents.registry import get_agent
from .jira.push_service import build_release_audit_pack

PLATFORM = "AI Agentic QE Platform"


def _agent_name(key: str) -> str:
    try:
        return get_agent(key).name
    except KeyError:
        return key


async def assemble(session: AsyncSession, story: Story) -> dict:
    """The structured evidence pack: immutable audit pack + enriched results."""
    pack = await build_release_audit_pack(session, story)
    latest = await referee._latest_runs(session, story.id)
    health = await referee.assess(session, story.id)

    agents = []
    for key, run in latest.items():
        o = run.output_json or {}
        agents.append({
            "agent_name": _agent_name(key),
            "agent_key": key,
            "phase": run.phase.value,
            "verdict": o.get("verdict"),
            "confidence": (o.get("confidence") or {}).get("level"),
            "release_blocking": bool(o.get("release_blocking")),
            "prompt_version": run.prompt_version,
            "model": run.model or "demo-fixture",
            "tokens": (run.token_usage or {}),
            "output_hash": run.output_hash,
            "summary": o.get("summary", ""),
        })
    agents.sort(key=lambda a: (a["phase"], a["agent_name"]))

    def out(key: str) -> dict:
        r = latest.get(key)
        return (r.output_json or {}) if r else {}

    regulatory = {
        "fca_impact": out("fca_regulatory_impact"),
        "consumer_duty": out("consumer_duty_mapper"),
        "financial_integrity": out("financial_data_integrity"),
        "fca_test_results": out("test_execution_analyst"),
        "audit_report_sections": out("regulatory_audit_trail").get("report_sections", []),
    }

    # Agents intentionally not run (disabled by the org's process) — the auditor
    # sees exactly what was skipped and why.
    skipped_rows = (
        await session.execute(
            select(AgentRun).where(
                AgentRun.story_id == story.id, AgentRun.status == RunStatus.SKIPPED
            )
        )
    ).scalars().all()
    skipped = [
        {"agent_name": _agent_name(r.agent_key), "phase": r.phase.value}
        for r in skipped_rows
    ]
    skipped.sort(key=lambda s: (s["phase"], s["agent_name"]))

    # Risk acceptances: what was knowingly accepted, by whom, and its review
    # state — the auditor's "show me what you tolerated" section.
    from . import risk_register

    register = await risk_register.list_register(session, story.id)
    pack["risk_acceptances"] = register

    pack["platform"] = PLATFORM
    pack["health"] = health
    pack["agents"] = agents
    pack["skipped_agents"] = skipped
    pack["regulatory"] = regulatory
    return pack


# --------------------------------------------------------------------- HTML


def _e(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


def _verdict_cls(v) -> str:
    return {"PASS": "ok", "WARN": "warn", "FAIL": "bad"}.get(v, "muted")


def _rows(items, cols):
    out = []
    for it in items:
        cells = "".join(f"<td>{c}</td>" for c in cols(it))
        out.append(f"<tr>{cells}</tr>")
    return "".join(out)


def render_html(pack: dict) -> str:
    s = pack["story"]
    h = pack["health"]
    chain = pack["audit_chain_verification"]
    reg = pack["regulatory"]
    chain_ok = chain.get("valid")

    gates_rows = _rows(
        pack["gates"],
        lambda g: [
            _e(g["phase"]),
            f'<span class="pill {"ok" if g["status"]=="SIGNED_OFF" else "muted"}">{_e(g["status"])}</span>',
            _e(g["approver_name"]), _e(g["approver_role"]),
            _e(g["rationale"]), _e(g["decided_at"]),
        ],
    )
    agent_rows = _rows(
        pack["agents"],
        lambda a: [
            _e(a["agent_name"]), _e(a["phase"]),
            f'<span class="pill {_verdict_cls(a["verdict"])}">{_e(a["verdict"])}</span>'
            + (' <span class="pill bad">BLOCKING</span>' if a["release_blocking"] else ""),
            _e(a["confidence"]), _e(a["prompt_version"]), _e(a["model"]),
            _e((a["tokens"] or {}).get("input_tokens", 0)) + "/" + _e((a["tokens"] or {}).get("output_tokens", 0)),
            f'<code>{_e((a["output_hash"] or "")[:16])}</code>',
        ],
    )
    risk_rows = _rows(
        (pack.get("risk_acceptances") or {}).get("entries", []),
        lambda r: [
            f'<span class="pill {"bad" if r["severity"] in ("BLOCKER", "CRITICAL", "HIGH") else "muted"}">{_e(r["severity"])}</span>',
            _e(r["title"]),
            _e(r["source"].replace("_", " ").lower()),
            _e(r["accepted_by"]),
            _e(r["rationale"] or "—"),
            f'{_e(r["status"])}{" · OVERDUE" if r["overdue"] else ""}',
            _e((r["review_by"] or "")[:10]),
        ],
    )
    event_rows = _rows(
        pack["audit_events"],
        lambda e: [
            _e(e["id"]), _e(e["created_at"]), _e(e["event_type"]),
            _e(e["actor"]), f'<code>{_e((e["event_hash"] or "")[:16])}</code>',
        ],
    )

    fin = reg["financial_integrity"]
    fin_rows = _rows(
        fin.get("checks", []),
        lambda c: [
            _e(c.get("name")), _e(c.get("category")), _e(c.get("expected")), _e(c.get("actual")),
            _e(c.get("variance")), _e(c.get("tolerance")),
            f'<span class="pill {"ok" if c.get("passed") else "bad"}">{"PASS" if c.get("passed") else "FAIL"}</span>',
        ],
    ) if fin.get("checks") else '<tr><td colspan="7" class="muted">No financial-integrity checks recorded.</td></tr>'

    cd_rows = _rows(
        reg["consumer_duty"].get("outcomes", []),
        lambda o: [_e(o.get("outcome")), _e(o.get("status")), _e(o.get("assessment"))],
    ) if reg["consumer_duty"].get("outcomes") else '<tr><td colspan="3" class="muted">Not assessed.</td></tr>'

    reg_map_rows = _rows(
        reg["fca_impact"].get("applicable_regulations", []),
        lambda r: [_e(r.get("handbook_ref")), _e(r.get("area")), _e(r.get("obligation"))],
    ) if reg["fca_impact"].get("applicable_regulations") else '<tr><td colspan="3" class="muted">Not assessed.</td></tr>'

    incons = h.get("inconsistencies", [])
    incons_html = (
        "".join(
            f'<li><span class="pill {_verdict_cls("FAIL" if i["severity"]=="HIGH" else "WARN")}">{_e(i["severity"])}</span> '
            f'<b>{_e(" ⇄ ".join(i["agents"]))}</b> — {_e(i["detail"])}</li>'
            for i in incons
        )
        if incons else '<li class="muted">No cross-agent inconsistencies detected.</li>'
    )

    audit_sections = "".join(
        f"<p><b>{_e(sec.get('section'))}.</b> {_e(sec.get('content'))}</p>"
        for sec in reg["audit_report_sections"]
    ) or '<p class="muted">Regulatory Audit Trail agent has not run.</p>'

    skipped = pack.get("skipped_agents", [])
    skipped_note = (
        '<p class="muted">⊘ Skipped by policy (disabled in settings, not run): '
        + ", ".join(f"{_e(s['agent_name'])} ({_e(s['phase'])})" for s in skipped)
        + ". Blocking-capable agents (FCA / financial integrity) cannot be disabled and always run.</p>"
        if skipped
        else '<p class="muted">No agents were skipped — the full configured pipeline ran.</p>'
    )

    band = h.get("band", "NO_DATA")
    band_cls = {"HEALTHY": "ok", "AT_RISK": "warn", "CRITICAL": "bad", "BLOCKED": "bad"}.get(band, "muted")

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Regulatory Evidence Pack — {_e(s['jira_key'])}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #1a1a1a;
          max-width: 1000px; margin: 0 auto; padding: 32px; font-size: 13px; line-height: 1.5; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 15px; margin: 28px 0 8px; border-bottom: 2px solid #1F4E78; padding-bottom: 4px; color: #1F4E78; }}
  table {{ width: 100%; border-collapse: collapse; margin: 6px 0; }}
  th, td {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid #e2e2e2; vertical-align: top; }}
  th {{ background: #f4f6f8; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #555; }}
  code {{ font-family: ui-monospace, Consolas, monospace; font-size: 11px; color: #444; }}
  .pill {{ display: inline-block; padding: 1px 7px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .ok {{ background: #e6f4ea; color: #137333; }}
  .warn {{ background: #fef7e0; color: #9c6500; }}
  .bad {{ background: #fce8e6; color: #c5221f; }}
  .muted {{ color: #888; }}
  .meta {{ color: #666; font-size: 12px; margin-bottom: 16px; }}
  .banner {{ padding: 10px 14px; border-radius: 8px; margin: 12px 0; font-weight: 600; }}
  .score {{ font-size: 30px; font-weight: 800; }}
  ul {{ margin: 6px 0; padding-left: 18px; }}
  @media print {{ body {{ padding: 0; }} h2 {{ page-break-after: avoid; }} }}
</style></head><body>

<h1>Regulatory Evidence Pack</h1>
<div class="meta">
  <b>{_e(s['jira_key'])}</b> — {_e(s['summary'])}<br>
  FCA impact: <b>{_e(s['fca_impact'])}</b> · Cloud: {_e(s['cloud'])} ·
  Released: {"Yes" if s.get('released') else "No"}<br>
  Generated {_e(pack['generated_at'])} by {_e(pack['platform'])}
</div>

<div class="banner {'ok' if chain_ok else 'bad'}">
  {'✓ Audit chain verified — ' + str(chain.get('events', 0)) + ' append-only events, tamper-evident.'
    if chain_ok else '✗ Audit chain FAILED verification: ' + _e(chain.get('reason', ''))}
</div>

<h2>1 · Release Health</h2>
<p><span class="score {band_cls}">{_e(h.get('score'))}</span> / 100 —
  <span class="pill {band_cls}">{_e(band)}</span> ·
  assurance {_e(h.get('assurance'))} · {_e(h.get('agents_evaluated'))} agents ·
  {_e(h['counts']['pass'])} pass / {_e(h['counts']['warn'])} warn / {_e(h['counts']['fail'])} fail</p>
<b>Cross-agent referee:</b><ul>{incons_html}</ul>

<h2>2 · Gate Sign-Offs (human approvals)</h2>
<table><thead><tr><th>Phase</th><th>Status</th><th>Approver</th><th>Role</th><th>Rationale</th><th>Decided</th></tr></thead>
<tbody>{gates_rows}</tbody></table>

<h2>3 · Regulatory Analysis</h2>
<p><b>FCA impact assessment:</b> {_e(reg['fca_impact'].get('impact_rationale', 'Not assessed.'))}</p>
<table><thead><tr><th>Handbook ref</th><th>Area</th><th>Obligation</th></tr></thead>
<tbody>{reg_map_rows}</tbody></table>
<p style="margin-top:10px"><b>Consumer Duty outcomes:</b></p>
<table><thead><tr><th>Outcome</th><th>Status</th><th>Assessment</th></tr></thead>
<tbody>{cd_rows}</tbody></table>

<h2>4 · Financial Data Integrity</h2>
<table><thead><tr><th>Check</th><th>Category</th><th>Expected</th><th>Actual</th><th>Variance</th><th>Tolerance</th><th>Result</th></tr></thead>
<tbody>{fin_rows}</tbody></table>

<h2>5 · AI Governance — Agent Execution Record</h2>
<p class="muted">Every agent run recorded with prompt version, model, token usage and output hash.</p>
<table><thead><tr><th>Agent</th><th>Phase</th><th>Verdict</th><th>Confidence</th><th>Prompt</th><th>Model</th><th>Tokens (in/out)</th><th>Output hash</th></tr></thead>
<tbody>{agent_rows}</tbody></table>
{skipped_note}

<h2>6 · Risk Acceptances (quality-debt register)</h2>
<p class="muted">Every knowingly-accepted risk: run accepted despite findings,
gate signed over WARN verdicts, or CONDITIONAL_GO — with owner, rationale and
review state.</p>
<table><thead><tr><th>Severity</th><th>Accepted risk</th><th>Source</th><th>Accepted by</th><th>Rationale</th><th>Status</th><th>Review by</th></tr></thead>
<tbody>{risk_rows or '<tr><td colspan="7" class="muted">No accepted risks on record — nothing was signed over findings.</td></tr>'}</tbody></table>

<h2>7 · Regulatory Audit Narrative</h2>
{audit_sections}

<h2>8 · Audit Event Log (append-only)</h2>
<table><thead><tr><th>#</th><th>Time</th><th>Event</th><th>Actor</th><th>Hash</th></tr></thead>
<tbody>{event_rows}</tbody></table>

<p class="meta" style="margin-top:24px">
  This pack is generated from the platform's append-only, hash-chained audit trail.
  Chain status at generation: {'VERIFIED' if chain_ok else 'FAILED'}.
</p>
</body></html>"""
