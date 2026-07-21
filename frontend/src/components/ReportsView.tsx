import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { MiPack, ReleaseSummary } from "../types";
import { useToast } from "../ui";

/** Stakeholder reporting — a report serves one decision, not one audience.
 *  Exec MI (per release, SEALED + hash-chained) · Flow (PM/PO, live) ·
 *  Quality (BA/QA, live) · Worklist (Dev, live). */

type SubTab = "exec" | "flow" | "quality" | "worklist";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

export function ReportsView({ actor }: { actor: string }) {
  const [sub, setSub] = useState<SubTab>("exec");
  return (
    <div className="stage">
      <div className="board-head">
        <div className="board-title">Reports</div>
        <div className="board-sub">Generated automatically at each gate &middot; signed and retained for FCA evidence</div>
      </div>
      <div className="navlinks" style={{ marginBottom: 16 }}>
        {(
          [
            ["exec", "Exec MI (per release)"],
            ["flow", "Flow (PM/PO)"],
            ["quality", "Quality (BA/QA)"],
            ["worklist", "Worklist (Dev)"],
          ] as [SubTab, string][]
        ).map(([id, label]) => (
          <button key={id} type="button" onClick={() => setSub(id)} className={sub === id ? "active" : ""}>
            {label}
          </button>
        ))}
      </div>
      {sub === "exec" && <ExecMi actor={actor} />}
      {sub === "flow" && <FlowView />}
      {sub === "quality" && <QualityView />}
      {sub === "worklist" && <WorklistView />}
    </div>
  );
}

// ---------------------------------------------------------------- Exec MI

function ExecMi({ actor }: { actor: string }) {
  const [name, setName] = useState("");
  const [date, setDate] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<MiPack | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();

  const releasesQ = useQuery({ queryKey: ["releases"], queryFn: () => api.releases() });
  const storiesQ = useQuery({ queryKey: ["stories"], queryFn: () => api.stories() });

  const create = useMutation({
    mutationFn: () => api.createRelease(actor, name, date, Array.from(selected)),
    onSuccess: () => {
      toast("ok", `Release "${name}" created.`);
      setName(""); setSelected(new Set());
      queryClient.invalidateQueries({ queryKey: ["releases"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });
  const seal = useMutation({
    mutationFn: (id: string) => api.sealMi(id, actor),
    onSuccess: (m) => {
      toast("ok", `MI pack sealed — hash ${m.payload_hash.slice(0, 10)}… recorded in the audit chain.`);
      queryClient.invalidateQueries({ queryKey: ["releases"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const releases = releasesQ.data ?? [];
  const stories = storiesQ.data ?? [];

  return (
    <div>
      <p className="mb-4 text-[11px] text-ink-dim">
        Board-ready Consumer-Duty-style MI. A sealed pack is immutable: its canonical
        hash enters the append-only audit chain, so "the numbers the board saw" stay
        reproducible. Live previews are clearly unsealed.
      </p>

      <div className="panel-block">
        <div className="section-label">New release</div>
        <div className="mb-2 flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='Name, e.g. "Release 26.8"'
            className="role-select"
            style={{ width: 220 }}
          />
          <input
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="Target date (YYYY-MM-DD)"
            className="role-select"
            style={{ width: 170 }}
          />
          <button
            type="button"
            className="sync-btn"
            disabled={!name.trim() || selected.size === 0 || create.isPending}
            onClick={() => {
              if (!actor.trim()) { toast("error", "Enter your name in the header first."); return; }
              create.mutate();
            }}
          >
            Create with {selected.size} story(ies)
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {stories.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => {
                const next = new Set(selected);
                if (next.has(s.id)) next.delete(s.id); else next.add(s.id);
                setSelected(next);
              }}
              className="chip"
              style={
                selected.has(s.id)
                  ? { color: "var(--color-accent)", borderColor: "var(--color-accent)", background: "var(--accent-soft)" }
                  : undefined
              }
            >
              {s.jira_key}
            </button>
          ))}
        </div>
      </div>

      {releases.length === 0 ? (
        <div className="panel-block text-center text-sm text-ink-faint">
          No releases yet — create one above to generate its MI pack.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {releases.map((r: ReleaseSummary) => (
            <div key={r.id} className="panel-block" style={{ marginBottom: 0 }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold text-ink">{r.name}</span>
                {r.target_date && (
                  <span className="font-mono text-[10px] text-ink-faint">→ {r.target_date}</span>
                )}
                <span className="chip">{r.story_ids.length} stories</span>
                <div className="ml-auto flex gap-2">
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={async () => {
                      try { setPreview(await api.miPreview(r.id)); }
                      catch (e) { toast("error", (e as Error).message); }
                    }}
                  >
                    Live preview
                  </button>
                  <button
                    type="button"
                    className="sync-btn"
                    disabled={seal.isPending}
                    onClick={() => {
                      if (!actor.trim()) { toast("error", "Enter your name in the header first."); return; }
                      seal.mutate(r.id);
                    }}
                  >
                    &#9990; Seal MI pack
                  </button>
                </div>
              </div>
              {r.snapshots.length > 0 && (
                <div className="mt-2 flex flex-col gap-1">
                  {r.snapshots.map((s) => (
                    <div key={s.id} className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
                      <span style={{ color: "var(--color-ok)" }}>&#9990; sealed</span>
                      <span className="text-ink-dim">{(s.created_at ?? "").slice(0, 16).replace("T", " ")}</span>
                      <span className="text-ink-faint">by {s.generated_by}</span>
                      <span className="text-[10px] text-ink-faint">#{s.payload_hash.slice(0, 12)}</span>
                      <button
                        className="text-accent hover:underline"
                        onClick={() => window.open(`/api/v1/reports/mi/${s.id}`, "_blank")}
                      >
                        open pack ↗
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {preview && <MiPreview pack={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}

function MiPreview({ pack, onClose }: { pack: MiPack; onClose: () => void }) {
  const ci = pack.confidence_index;
  return (
    <div className="referee" style={{ marginTop: 16, borderColor: "var(--warn-soft)" }}>
      <div className="mb-2 flex items-center gap-2">
        <span className="pill pill-warn">Unsealed preview</span>
        <span className="text-[13px] font-semibold text-ink">{pack.release.name}</span>
        <span className="font-mono text-[10px] text-ink-faint">numbers may still move — seal to freeze</span>
        <button type="button" className="ghost-btn ml-auto" onClick={onClose}>&#10005;</button>
      </div>
      <div className="kpi-row" style={{ marginBottom: 12 }}>
        {[
          ["Confidence index", ci === null ? "—" : String(ci),
           ci !== null && ci >= 80 ? "var(--color-ok)" : ci !== null && ci >= 55 ? "var(--color-warn)" : "var(--color-bad)"],
          ["Open risks (overdue)", `${pack.quality_debt.open} (${pack.quality_debt.overdue})`,
           pack.quality_debt.overdue ? "var(--color-bad)" : undefined],
          ["FCA scenarios unexecuted", String(pack.regulatory_evidence.fca_scenarios_unexecuted),
           pack.regulatory_evidence.fca_scenarios_unexecuted ? "var(--color-bad)" : "var(--color-ok)"],
          ["Runs human-decided", pct(pack.ai_governance.human_decided_pct), undefined],
        ].map(([label, val, color]) => (
          <div key={label as string} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 20, color: color as string | undefined }}>{val}</div>
          </div>
        ))}
      </div>
      <div className="dtable" style={{ overflowX: "auto" }}>
        <table style={{ width: "100%" }}>
          <thead>
            <tr><th>Story</th><th>Phase</th><th>Health</th><th>Blockers</th><th>Released</th></tr>
          </thead>
          <tbody>
            {pack.stories.map((s) => (
              <tr key={s.jira_key}>
                <td className="idcell">{s.jira_key}</td>
                <td>{s.phase}</td>
                <td style={{
                  color: s.band === "HEALTHY" ? "var(--color-ok)" : s.band === "AT_RISK" ? "var(--color-warn)" : s.band === "NO_DATA" ? "var(--color-ink-faint)" : "var(--color-bad)",
                }}>
                  {s.score ?? "—"} · {s.band}
                </td>
                <td>{s.blockers}</td>
                <td>{s.released ? "Yes" : "No"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 font-mono text-[10px] text-ink-faint">
        Lead time {pack.flow.avg_lead_time_days ?? "—"}d · rework rate {pct(pack.flow.rework_story_rate)} ·
        override rate {pct(pack.ai_governance.override_rate)} · first-time-right {pct(pack.ai_governance.first_time_right_rate)}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Flow

function FlowView() {
  const q = useQuery({ queryKey: ["flow-report"], queryFn: () => api.flowReport() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  return (
    <div>
      <p className="mb-4 text-[11px] text-ink-dim">
        Live. Gate cycle times, the human-in-the-loop queue, and blocking questions aging.
      </p>
      <div className="kpi-row">
        {[
          ["HITL queue depth", String(d.hitl_queue.depth)],
          ["Avg decision latency", d.hitl_queue.avg_decision_latency_days === null ? "—" : `${d.hitl_queue.avg_decision_latency_days}d`],
          ["Blocking questions open", String(d.blocking_questions.length)],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 22 }}>{val}</div>
          </div>
        ))}
      </div>

      {d.gate_cycle_times.length > 0 && (
        <div className="panel-block">
          <div className="section-label">Gate cycle time</div>
          <div className="flex gap-4 text-[12px] text-ink">
            {d.gate_cycle_times.map((g) => (
              <span key={g.phase}>{g.phase}: <b>{g.avg_days}d</b> ({g.gates})</span>
            ))}
          </div>
        </div>
      )}

      <div className="panel-block">
        <div className="section-label">Waiting on a human (oldest first)</div>
        {d.hitl_queue.runs.length === 0 && d.hitl_queue.gates_ready.length === 0 ? (
          <div className="text-[11px] text-ink-faint">Queue clear.</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {d.hitl_queue.gates_ready.map((g, i) => (
              <div key={`g${i}`} className="flex items-center gap-2">
                <span className="pill" style={{ color: "var(--color-review)", borderColor: "var(--color-review)" }}>Gate</span>
                <span className="card-id">{g.jira_key}</span>
                <span className="text-[12px] text-ink">{g.phase} sign-off ready</span>
                <span className="ml-auto font-mono text-[10px]" style={{ color: g.age_days > 2 ? "var(--color-bad)" : "var(--color-ink-faint)" }}>{g.age_days}d</span>
              </div>
            ))}
            {d.hitl_queue.runs.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="pill pill-slate">{r.kind === "RUN_APPROVAL" ? "Approve" : "Decide"}</span>
                <span className="card-id">{r.jira_key}</span>
                <span className="text-[12px] text-ink">{r.agent}</span>
                <span className="ml-auto font-mono text-[10px]" style={{ color: r.age_days > 2 ? "var(--color-bad)" : "var(--color-ink-faint)" }}>{r.age_days}d</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {d.blocking_questions.length > 0 && (
        <div className="referee" style={{ background: "var(--crit-soft)", borderColor: "var(--crit-soft)", borderLeftColor: "var(--color-bad)" }}>
          <div className="referee-kicker">Blocking questions aging</div>
          {d.blocking_questions.map((bq, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 py-1 text-[12px]">
              <span className="card-id">{bq.jira_key}</span>
              <span className="text-ink">{bq.question}</span>
              <span className="font-mono text-[10px] text-ink-faint">→ {bq.owner?.replaceAll("_", " ").toLowerCase()}</span>
              <span className="ml-auto font-mono text-[10px]" style={{ color: "var(--color-bad)" }}>{bq.age_days}d</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- Quality

function QualityView() {
  const q = useQuery({ queryKey: ["quality-report"], queryFn: () => api.qualityReport() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  const p = d.test_pyramid;
  return (
    <div>
      <p className="mb-4 text-[11px] text-ink-dim">
        Live. Traceability integrity (the real RTM), pyramid shape, first-time-right per
        agent, and the flake index.
      </p>
      <div className="kpi-row">
        {[
          ["Pyramid (unit/api/ui)", `${p.unit}/${p.api}/${p.ui}`],
          ["Uncovered example cards", String(d.uncovered_example_cards)],
          ["Flaky signatures (high)", `${d.flake_index.total} (${d.flake_index.high_score})`],
          ["Expired quarantines", String(d.flake_index.expired_quarantines)],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 20 }}>{val}</div>
          </div>
        ))}
      </div>

      {d.traceability.length > 0 && (
        <div className="panel-block" style={{ padding: 0 }}>
          <div className="dtable" style={{ padding: 20, overflowX: "auto" }}>
            <table style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Story</th><th>ACs</th><th>Covered</th><th>Partial</th><th>Not covered</th>
                </tr>
              </thead>
              <tbody>
                {d.traceability.map((t) => (
                  <tr key={t.jira_key}>
                    <td className="idcell">{t.jira_key}</td>
                    <td>{t.ac_total}</td>
                    <td style={{ color: "var(--color-ok)" }}>{t.covered}</td>
                    <td style={{ color: "var(--color-warn)" }}>{t.partial}</td>
                    <td style={{ color: t.not_covered ? "var(--color-bad)" : "var(--color-ink-dim)" }}>{t.not_covered}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {d.first_time_right.length > 0 && (
        <div className="panel-block">
          <div className="section-label">First-time-right per agent (lowest first — most human rework)</div>
          <div className="flex flex-col gap-1.5">
            {d.first_time_right.map((f) => (
              <div key={f.agent_key} className="flex items-center gap-2 text-[12px]">
                <span className="text-ink">{f.agent_name}</span>
                <span
                  className="ml-auto font-mono"
                  style={{ color: f.first_time_right_rate >= 0.8 ? "var(--color-ok)" : "var(--color-warn)" }}
                >
                  {pct(f.first_time_right_rate)} of {f.accepted}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- Worklist

const SEV_PILL: Record<string, string> = {
  BLOCKER: "pill-crit",
  CRITICAL: "pill-crit",
  HIGH: "pill-crit",
  MEDIUM: "pill-warn",
  LOW: "pill-slate",
};

function WorklistView() {
  const storiesQ = useQuery({ queryKey: ["stories"], queryFn: () => api.stories() });
  const [storyId, setStoryId] = useState("");
  const wlQ = useQuery({
    queryKey: ["worklist", storyId],
    queryFn: () => api.worklist(storyId),
    enabled: !!storyId,
  });
  const stories = storiesQ.data ?? [];
  const d = wlQ.data;
  return (
    <div>
      <p className="mb-3 text-[11px] text-ink-dim">
        Live. Every finding across the story's latest runs, strongest first.
      </p>
      <select
        value={storyId}
        onChange={(e) => setStoryId(e.target.value)}
        className="role-select mb-3"
      >
        <option value="">Select a story…</option>
        {stories.map((s) => (
          <option key={s.id} value={s.id}>{s.jira_key} — {s.summary.slice(0, 60)}</option>
        ))}
      </select>
      {d && (
        d.items.length === 0 ? (
          <div className="panel-block text-center text-sm text-ink-faint">
            No findings — nothing to fix on this story right now.
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {d.items.map((i, idx) => (
              <div key={idx} className="panel-block" style={{ marginBottom: 0, padding: "10px 14px" }}>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={`pill ${SEV_PILL[i.severity] ?? "pill-slate"}`}>{i.severity}</span>
                  <span className="text-[13px] font-medium text-ink">{i.title}</span>
                  <span className="ml-auto font-mono text-[10px] text-ink-faint">
                    {i.agent_name} · {i.phase}
                  </span>
                </div>
                {i.detail && <div className="mt-1 text-[11.5px] text-ink-dim">{i.detail}</div>}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
