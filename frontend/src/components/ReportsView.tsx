import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { MiPack, ReleaseSummary } from "../types";
import { Badge, Button, useToast } from "../ui";

/** Stakeholder reporting — a report serves one decision, not one audience.
 *  Exec MI (per release, SEALED + hash-chained) · Flow (PM/PO, live) ·
 *  Quality (BA/QA, live) · Worklist (Dev, live). */

type SubTab = "exec" | "flow" | "quality" | "worklist";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

export function ReportsView({ actor }: { actor: string }) {
  const [sub, setSub] = useState<SubTab>("exec");
  return (
    <div className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex gap-1">
        {(
          [
            ["exec", "Exec MI (per release)"],
            ["flow", "Flow (PM/PO)"],
            ["quality", "Quality (BA/QA)"],
            ["worklist", "Worklist (Dev)"],
          ] as [SubTab, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setSub(id)}
            className={`rounded px-2.5 py-1 text-[11px] font-medium ${
              sub === id ? "bg-accent/15 text-accent" : "text-ink-dim hover:bg-panel-2"
            }`}
          >
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
      <h2 className="mb-1 text-sm font-semibold text-ink">Executive MI — per release, sealed</h2>
      <p className="mb-4 text-[11px] text-ink-dim">
        Board-ready Consumer-Duty-style MI. A sealed pack is immutable: its canonical
        hash enters the append-only audit chain, so "the numbers the board saw" stay
        reproducible. Live previews are clearly unsealed.
      </p>

      {/* Create release */}
      <div className="mb-5 rounded-lg border border-line bg-panel p-3">
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          New release
        </h3>
        <div className="mb-2 flex flex-wrap gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder='Name, e.g. "Release 26.8"'
            className="w-56 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
          />
          <input
            value={date}
            onChange={(e) => setDate(e.target.value)}
            placeholder="Target date (YYYY-MM-DD)"
            className="w-44 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
          />
          <Button
            variant="primary"
            disabled={!name.trim() || selected.size === 0}
            busy={create.isPending}
            onClick={() => {
              if (!actor.trim()) { toast("error", "Enter your name in the header first."); return; }
              create.mutate();
            }}
          >
            Create with {selected.size} story(ies)
          </Button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {stories.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                const next = new Set(selected);
                if (next.has(s.id)) next.delete(s.id); else next.add(s.id);
                setSelected(next);
              }}
              className={`rounded border px-2 py-0.5 font-mono text-[10px] ${
                selected.has(s.id)
                  ? "border-accent/60 bg-accent/15 text-accent"
                  : "border-line text-ink-dim hover:bg-panel-2"
              }`}
            >
              {s.jira_key}
            </button>
          ))}
        </div>
      </div>

      {/* Releases + snapshots */}
      {releases.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No releases yet — create one above to generate its MI pack.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {releases.map((r: ReleaseSummary) => (
            <div key={r.id} className="rounded-lg border border-line bg-panel p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-semibold text-ink">{r.name}</span>
                {r.target_date && (
                  <span className="font-mono text-[10px] text-ink-faint">→ {r.target_date}</span>
                )}
                <Badge className="border-line text-ink-dim">{r.story_ids.length} stories</Badge>
                <div className="ml-auto flex gap-2">
                  <Button
                    onClick={async () => {
                      try { setPreview(await api.miPreview(r.id)); }
                      catch (e) { toast("error", (e as Error).message); }
                    }}
                  >
                    👁 Live preview
                  </Button>
                  <Button
                    variant="primary"
                    busy={seal.isPending}
                    onClick={() => {
                      if (!actor.trim()) { toast("error", "Enter your name in the header first."); return; }
                      seal.mutate(r.id);
                    }}
                  >
                    ✒ Seal MI pack
                  </Button>
                </div>
              </div>
              {r.snapshots.length > 0 && (
                <div className="mt-2 flex flex-col gap-1">
                  {r.snapshots.map((s) => (
                    <div key={s.id} className="flex flex-wrap items-center gap-2 text-[11px]">
                      <span className="text-ok">✒ sealed</span>
                      <span className="text-ink-dim">{(s.created_at ?? "").slice(0, 16).replace("T", " ")}</span>
                      <span className="text-ink-faint">by {s.generated_by}</span>
                      <span className="font-mono text-[10px] text-ink-faint">#{s.payload_hash.slice(0, 12)}</span>
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
    <div className="mt-4 rounded-lg border border-warn/40 bg-warn/5 p-3">
      <div className="mb-2 flex items-center gap-2">
        <Badge className="border-warn/50 bg-warn/10 text-warn">UNSEALED PREVIEW</Badge>
        <span className="text-xs font-semibold text-ink">{pack.release.name}</span>
        <span className="text-[10px] text-ink-faint">numbers may still move — seal to freeze</span>
        <Button variant="ghost" onClick={onClose}>✕</Button>
      </div>
      <div className="grid grid-cols-4 gap-3">
        {[
          ["Confidence index", ci === null ? "—" : String(ci),
           ci !== null && ci >= 80 ? "text-ok" : ci !== null && ci >= 55 ? "text-warn" : "text-bad"],
          ["Open risks (overdue)", `${pack.quality_debt.open} (${pack.quality_debt.overdue})`,
           pack.quality_debt.overdue ? "text-bad" : "text-ink"],
          ["FCA scenarios unexecuted", String(pack.regulatory_evidence.fca_scenarios_unexecuted),
           pack.regulatory_evidence.fca_scenarios_unexecuted ? "text-bad" : "text-ok"],
          ["Runs human-decided", pct(pack.ai_governance.human_decided_pct), "text-ink"],
        ].map(([label, val, cls]) => (
          <div key={label as string} className="rounded border border-line bg-panel p-2">
            <div className={`text-base font-bold ${cls}`}>{val}</div>
            <div className="text-[9px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>
      <table className="mt-3 w-full text-left text-[11px]">
        <thead>
          <tr className="border-b border-line text-[10px] uppercase text-ink-faint">
            <th className="py-1 pr-2">Story</th><th className="py-1 pr-2">Phase</th>
            <th className="py-1 pr-2">Health</th><th className="py-1 pr-2">Blockers</th>
            <th className="py-1">Released</th>
          </tr>
        </thead>
        <tbody>
          {pack.stories.map((s) => (
            <tr key={s.jira_key} className="border-b border-line/50">
              <td className="py-1 pr-2 font-mono text-accent">{s.jira_key}</td>
              <td className="py-1 pr-2">{s.phase}</td>
              <td className={`py-1 pr-2 ${s.band === "HEALTHY" ? "text-ok" : s.band === "AT_RISK" ? "text-warn" : s.band === "NO_DATA" ? "text-ink-faint" : "text-bad"}`}>
                {s.score ?? "—"} · {s.band}
              </td>
              <td className="py-1 pr-2">{s.blockers}</td>
              <td className="py-1">{s.released ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 text-[10px] text-ink-faint">
        Lead time {pack.flow.avg_lead_time_days ?? "—"}d · rework rate {pct(pack.flow.rework_story_rate)} ·
        override rate {pct(pack.ai_governance.override_rate)} · first-time-right {pct(pack.ai_governance.first_time_right_rate)}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Flow

const innerTabCls = (active: boolean) =>
  `rounded px-2 py-1 text-[10px] font-medium ${
    active ? "bg-accent/15 text-accent" : "text-ink-dim hover:bg-panel-2"
  }`;

function FlowView() {
  const [inner, setInner] = useState<"queue" | "sla" | "readiness">("queue");
  return (
    <div>
      <h2 className="mb-1 text-sm font-semibold text-ink">Flow — where is work stuck?</h2>
      <p className="mb-3 text-[11px] text-ink-dim">
        Live. Gate cycle times and the human-in-the-loop queue (PM), SLA breaches (PM) and
        release readiness / scope-risk (PO).
      </p>
      <div className="mb-4 flex gap-1">
        {(
          [
            ["queue", "Queue & cycle time"],
            ["sla", "SLA breaches"],
            ["readiness", "Readiness (PO)"],
          ] as [typeof inner, string][]
        ).map(([id, label]) => (
          <button key={id} onClick={() => setInner(id)} className={innerTabCls(inner === id)}>
            {label}
          </button>
        ))}
      </div>
      {inner === "queue" && <FlowQueuePanel />}
      {inner === "sla" && <SlaBreachesPanel />}
      {inner === "readiness" && <ReadinessPanel />}
    </div>
  );
}

function FlowQueuePanel() {
  const q = useQuery({ queryKey: ["flow-report"], queryFn: () => api.flowReport() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  return (
    <div>
      <div className="mb-4 grid grid-cols-3 gap-3">
        {[
          ["HITL queue depth", String(d.hitl_queue.depth)],
          ["Avg decision latency", d.hitl_queue.avg_decision_latency_days === null ? "—" : `${d.hitl_queue.avg_decision_latency_days}d`],
          ["Blocking questions open", String(d.blocking_questions.length)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {d.gate_cycle_times.length > 0 && (
        <div className="mb-4 rounded-lg border border-line bg-panel p-3">
          <h3 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">Gate cycle time</h3>
          <div className="flex gap-4 text-[11px] text-ink">
            {d.gate_cycle_times.map((g) => (
              <span key={g.phase}>{g.phase}: <b>{g.avg_days}d</b> ({g.gates})</span>
            ))}
          </div>
        </div>
      )}

      <div className="mb-4 rounded-lg border border-line bg-panel p-3">
        <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Waiting on a human (oldest first)
        </h3>
        {d.hitl_queue.runs.length === 0 && d.hitl_queue.gates_ready.length === 0 ? (
          <div className="text-[11px] text-ink-faint">Queue clear.</div>
        ) : (
          <div className="flex flex-col gap-1 text-[11px]">
            {d.hitl_queue.gates_ready.map((g, i) => (
              <div key={`g${i}`} className="flex gap-2">
                <Badge className="border-review/40 text-review">GATE</Badge>
                <span className="font-mono text-accent">{g.jira_key}</span>
                <span className="text-ink">{g.phase} sign-off ready</span>
                <span className={`ml-auto font-mono text-[10px] ${g.age_days > 2 ? "text-bad" : "text-ink-faint"}`}>{g.age_days}d</span>
              </div>
            ))}
            {d.hitl_queue.runs.map((r, i) => (
              <div key={i} className="flex gap-2">
                <Badge className="border-line text-ink-dim">{r.kind === "RUN_APPROVAL" ? "APPROVE" : "DECIDE"}</Badge>
                <span className="font-mono text-accent">{r.jira_key}</span>
                <span className="text-ink">{r.agent}</span>
                <span className={`ml-auto font-mono text-[10px] ${r.age_days > 2 ? "text-bad" : "text-ink-faint"}`}>{r.age_days}d</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {d.blocking_questions.length > 0 && (
        <div className="rounded-lg border border-bad/40 bg-bad/5 p-3">
          <h3 className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-bad">
            Blocking questions aging
          </h3>
          {d.blocking_questions.map((bq, i) => (
            <div key={i} className="flex flex-wrap gap-2 text-[11px]">
              <span className="font-mono text-accent">{bq.jira_key}</span>
              <span className="text-ink">{bq.question}</span>
              <span className="text-ink-faint">→ {bq.owner?.replaceAll("_", " ").toLowerCase()}</span>
              <span className="ml-auto font-mono text-[10px] text-bad">{bq.age_days}d</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SlaBreachesPanel() {
  const q = useQuery({ queryKey: ["sla-breaches"], queryFn: () => api.slaBreaches() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  return (
    <div>
      <p className="mb-3 text-[11px] text-ink-dim">
        HITL items past their phase's SLA threshold — the standup escalation list, not the
        full queue. Thresholds (days):{" "}
        {Object.entries(d.thresholds).map(([p, v]) => `${p} ${v}`).join(" · ")} (Settings &gt; sla).
      </p>
      {d.breaches.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No breaches — everything is within its SLA.
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {d.breaches.map((b, i) => (
            <div
              key={i}
              className="flex flex-wrap items-center gap-2 rounded-lg border border-bad/40 bg-bad/5 px-3 py-2 text-[11px]"
            >
              <Badge className="border-bad/50 bg-bad/10 text-bad">{b.kind}</Badge>
              <span className="font-mono text-accent">{b.jira_key}</span>
              <span className="text-ink">{b.agent ?? `${b.phase} sign-off`}</span>
              <span className="text-[10px] uppercase tracking-wider text-ink-faint">{b.phase}</span>
              <span className="ml-auto font-mono text-[10px] text-bad">
                {b.age_days}d · over by {b.over_by_days}d (limit {b.threshold_days}d)
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ReadinessPanel() {
  const q = useQuery({ queryKey: ["readiness"], queryFn: () => api.readiness() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  const RISK_CLS: Record<string, string> = {
    HIGH: "border-bad/50 bg-bad/10 text-bad",
    MEDIUM: "border-warn/50 bg-warn/10 text-warn",
    LOW: "border-line text-ink-dim",
  };
  return (
    <div>
      <p className="mb-3 text-[11px] text-ink-dim">
        Every active, unreleased story, scope-risk first — what to descope now, while there's
        still time to react.
      </p>
      <div className="mb-3 grid grid-cols-3 gap-3">
        {[
          ["Total", String(d.summary.total)],
          ["High risk", String(d.summary.high_risk)],
          ["Medium risk", String(d.summary.medium_risk)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>
      {d.stories.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No active, unreleased stories.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[10px] uppercase tracking-wider text-ink-faint">
                <th className="px-3 py-2">Story</th><th className="px-3 py-2">Phase</th>
                <th className="px-3 py-2">Health</th><th className="px-3 py-2">Risks (overdue)</th>
                <th className="px-3 py-2">Target date</th><th className="px-3 py-2">Scope risk</th>
              </tr>
            </thead>
            <tbody>
              {d.stories.map((s) => (
                <tr key={s.jira_key} className="border-b border-line/50">
                  <td className="px-3 py-1.5 font-mono text-accent">{s.jira_key}</td>
                  <td className="px-3 py-1.5">{s.phase}</td>
                  <td className="px-3 py-1.5">{s.score ?? "—"} · {s.band}</td>
                  <td className={`px-3 py-1.5 ${s.overdue_risks ? "text-bad" : ""}`}>
                    {s.open_risks} ({s.overdue_risks})
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[10px] text-ink-faint">
                    {s.target_date ?? "—"}{s.days_to_target !== null && ` (${s.days_to_target}d)`}
                  </td>
                  <td className="px-3 py-1.5">
                    <Badge className={RISK_CLS[s.scope_risk]}>{s.scope_risk}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- Quality

function QualityView() {
  const [inner, setInner] = useState<"overview" | "ambiguity">("overview");
  return (
    <div>
      <h2 className="mb-1 text-sm font-semibold text-ink">Quality — is it proven?</h2>
      <p className="mb-3 text-[11px] text-ink-dim">
        Live. Traceability, pyramid shape, first-time-right and flake index (BA/QA), plus
        unresolved AC ambiguity (BA/QA).
      </p>
      <div className="mb-4 flex gap-1">
        {(
          [
            ["overview", "Overview"],
            ["ambiguity", "AC ambiguity"],
          ] as [typeof inner, string][]
        ).map(([id, label]) => (
          <button key={id} onClick={() => setInner(id)} className={innerTabCls(inner === id)}>
            {label}
          </button>
        ))}
      </div>
      {inner === "overview" && <QualityOverviewPanel />}
      {inner === "ambiguity" && <AcAmbiguityPanel />}
    </div>
  );
}

function QualityOverviewPanel() {
  const q = useQuery({ queryKey: ["quality-report"], queryFn: () => api.qualityReport() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  const p = d.test_pyramid;
  return (
    <div>
      <div className="mb-4 grid grid-cols-4 gap-3">
        {[
          ["Pyramid (unit/api/ui)", `${p.unit}/${p.api}/${p.ui}`],
          ["Uncovered example cards", String(d.uncovered_example_cards)],
          ["Flaky signatures (high)", `${d.flake_index.total} (${d.flake_index.high_score})`],
          ["Expired quarantines", String(d.flake_index.expired_quarantines)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {d.traceability.length > 0 && (
        <div className="mb-4 overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[10px] uppercase tracking-wider text-ink-faint">
                <th className="px-3 py-2">Story</th><th className="px-3 py-2">ACs</th>
                <th className="px-3 py-2">Covered</th><th className="px-3 py-2">Partial</th>
                <th className="px-3 py-2">Not covered</th>
              </tr>
            </thead>
            <tbody>
              {d.traceability.map((t) => (
                <tr key={t.jira_key} className="border-b border-line/50">
                  <td className="px-3 py-1.5 font-mono text-accent">{t.jira_key}</td>
                  <td className="px-3 py-1.5">{t.ac_total}</td>
                  <td className="px-3 py-1.5 text-ok">{t.covered}</td>
                  <td className="px-3 py-1.5 text-warn">{t.partial}</td>
                  <td className={`px-3 py-1.5 ${t.not_covered ? "text-bad" : "text-ink-dim"}`}>{t.not_covered}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {d.first_time_right.length > 0 && (
        <div className="rounded-lg border border-line bg-panel p-3">
          <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            First-time-right per agent (lowest first — most human rework)
          </h3>
          <div className="flex flex-col gap-1 text-[11px]">
            {d.first_time_right.map((f) => (
              <div key={f.agent_key} className="flex gap-2">
                <span className="text-ink">{f.agent_name}</span>
                <span className={`ml-auto font-mono ${f.first_time_right_rate >= 0.8 ? "text-ok" : "text-warn"}`}>
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

function AcAmbiguityPanel() {
  const q = useQuery({ queryKey: ["ac-ambiguity"], queryFn: () => api.acAmbiguity() });
  const d = q.data;
  if (!d) return <div className="text-sm text-ink-faint">Loading…</div>;
  return (
    <div>
      <p className="mb-3 text-[11px] text-ink-dim">
        Unresolved Three Amigos open questions, grouped by story — what to clarify with the
        PO before dev starts, not after.
      </p>
      <div className="mb-3 grid grid-cols-3 gap-3">
        {[
          ["Stories with open questions", String(d.summary.stories_with_open_questions)],
          ["Blocking", String(d.summary.stories_blocking)],
          ["Escalations (past Refinement)", String(d.summary.escalations)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className={`text-lg font-bold ${label.startsWith("Escalations") && d.summary.escalations > 0 ? "text-bad" : "text-ink"}`}>
              {val}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>
      {d.stories.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No open AC questions.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {d.stories.map((s) => (
            <div
              key={s.jira_key}
              className={`rounded-lg border bg-panel p-3 ${s.escalate ? "border-bad/60" : "border-line"}`}
            >
              <div className="mb-1.5 flex items-center gap-2">
                <span className="font-mono text-[11px] text-accent">{s.jira_key}</span>
                <span className="text-[10px] uppercase tracking-wider text-ink-faint">{s.phase}</span>
                {s.escalate && (
                  <Badge className="border-bad/70 bg-bad/20 font-bold text-bad">
                    ESCALATE — moved past Refinement unresolved
                  </Badge>
                )}
              </div>
              <div className="flex flex-col gap-1">
                {s.blocking.map((bq, i) => (
                  <div key={`b${i}`} className="flex flex-wrap gap-2 text-[11px]">
                    <Badge className="border-bad/50 bg-bad/10 text-bad">BLOCKING</Badge>
                    <span className="text-ink">{bq.question}</span>
                    <span className="ml-auto text-ink-faint">→ {bq.owner?.replaceAll("_", " ").toLowerCase()}</span>
                  </div>
                ))}
                {s.non_blocking.map((nq, i) => (
                  <div key={`n${i}`} className="flex flex-wrap gap-2 text-[11px]">
                    <Badge className="border-line text-ink-dim">OPEN</Badge>
                    <span className="text-ink-dim">{nq.question}</span>
                    <span className="ml-auto text-ink-faint">→ {nq.owner?.replaceAll("_", " ").toLowerCase()}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------- Worklist

function WorklistView() {
  const [inner, setInner] = useState<"findings" | "overrides">("findings");
  return (
    <div>
      <h2 className="mb-1 text-sm font-semibold text-ink">Worklist — what do I fix?</h2>
      <p className="mb-3 text-[11px] text-ink-dim">
        Live. Every finding across a story's latest runs, strongest first — plus why agent
        output on your stories got overridden.
      </p>
      <div className="mb-3 flex gap-1">
        {(
          [
            ["findings", "Findings"],
            ["overrides", "Why overridden"],
          ] as [typeof inner, string][]
        ).map(([id, label]) => (
          <button key={id} onClick={() => setInner(id)} className={innerTabCls(inner === id)}>
            {label}
          </button>
        ))}
      </div>
      {inner === "findings" && <WorklistFindingsPanel />}
      {inner === "overrides" && <OverridesPanel />}
    </div>
  );
}

function WorklistFindingsPanel() {
  const storiesQ = useQuery({ queryKey: ["stories"], queryFn: () => api.stories() });
  const [storyId, setStoryId] = useState("");
  const wlQ = useQuery({
    queryKey: ["worklist", storyId],
    queryFn: () => api.worklist(storyId),
    enabled: !!storyId,
  });
  const stories = storiesQ.data ?? [];
  const d = wlQ.data;
  const SEV: Record<string, string> = {
    BLOCKER: "border-bad/70 bg-bad/20 text-bad font-bold",
    CRITICAL: "border-bad/50 bg-bad/10 text-bad",
    HIGH: "border-bad/40 bg-bad/5 text-bad",
    MEDIUM: "border-warn/50 bg-warn/10 text-warn",
    LOW: "border-line text-ink-dim",
  };
  return (
    <div>
      <select
        value={storyId}
        onChange={(e) => setStoryId(e.target.value)}
        className="mb-3 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
      >
        <option value="">Select a story…</option>
        {stories.map((s) => (
          <option key={s.id} value={s.id}>{s.jira_key} — {s.summary.slice(0, 60)}</option>
        ))}
      </select>
      {d && (
        d.items.length === 0 ? (
          <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
            No findings — nothing to fix on this story right now.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {d.items.map((i, idx) => (
              <div key={idx} className="rounded border border-line bg-panel px-3 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge className={SEV[i.severity] ?? "border-line text-ink-dim"}>{i.severity}</Badge>
                  <span className="text-xs font-medium text-ink">{i.title}</span>
                  <span className="ml-auto font-mono text-[10px] text-ink-faint">
                    {i.agent_name} · {i.phase}
                  </span>
                </div>
                {i.detail && <div className="mt-0.5 text-[11px] text-ink-dim">{i.detail}</div>}
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}

function OverridesPanel() {
  const [assignee, setAssignee] = useState("");
  const q = useQuery({
    queryKey: ["overrides", assignee],
    queryFn: () => api.overrides(assignee.trim() || undefined),
  });
  const d = q.data;
  return (
    <div>
      <p className="mb-3 text-[11px] text-ink-dim">
        Rejection reasons and re-run guidance for your stories' runs, grouped by agent —
        how to brief the agent better, or spot a real bug.
      </p>
      <input
        value={assignee}
        onChange={(e) => setAssignee(e.target.value)}
        placeholder="Filter by assignee (exact name)…"
        className="mb-3 w-64 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
      />
      {!d ? (
        <div className="text-sm text-ink-faint">Loading…</div>
      ) : d.agents.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No overrides recorded{assignee.trim() ? ` for ${assignee.trim()}` : ""}.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {d.agents.map((a) => (
            <div key={a.agent_key} className="rounded-lg border border-line bg-panel p-3">
              <div className="mb-1.5 flex items-center gap-2">
                <span className="text-xs font-semibold text-ink">{a.agent_name}</span>
                <Badge className="border-line text-ink-dim">{a.count}</Badge>
              </div>
              <div className="flex flex-col gap-1">
                {a.items.map((it, i) => (
                  <div key={i} className="flex flex-wrap gap-2 text-[11px]">
                    <Badge
                      className={
                        it.kind === "REJECTED"
                          ? "border-bad/50 bg-bad/10 text-bad"
                          : "border-warn/50 bg-warn/10 text-warn"
                      }
                    >
                      {it.kind === "REJECTED" ? "REJECTED" : "RE-RUN"}
                    </Badge>
                    <span className="font-mono text-accent">{it.jira_key}</span>
                    <span className="text-ink-dim">{it.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
