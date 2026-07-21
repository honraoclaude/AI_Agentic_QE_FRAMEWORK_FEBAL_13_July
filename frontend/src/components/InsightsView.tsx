import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { AgentPerf, FlakySig } from "../types";
import { useToast } from "../ui";

function trustColor(t: number | null): string {
  if (t === null) return "var(--color-ink-faint)";
  if (t >= 85) return "var(--color-ok)";
  if (t >= 60) return "var(--color-warn)";
  return "var(--color-bad)";
}

function TrustBar({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-faint">—</span>;
  return (
    <div className="flex items-center">
      <span className="bar-track">
        <span className="bar-fill" style={{ width: `${value}%`, background: trustColor(value) }} />
      </span>
      <span className="font-mono text-[11px]" style={{ color: trustColor(value) }}>{value}</span>
    </div>
  );
}

function AgentRow({ a }: { a: AgentPerf }) {
  return (
    <tr>
      <td>
        <div className="text-ink">{a.agent_name}</div>
        <div className="font-mono text-[9.5px] uppercase tracking-wider text-ink-faint">{a.phase}</div>
      </td>
      <td><TrustBar value={a.trust_score} /></td>
      <td className="mono">
        <span style={{ color: "var(--color-ok)" }}>{a.accepted}✓</span>{" "}
        <span style={{ color: "var(--color-bad)" }}>{a.rejected}✗</span>{" "}
        <span style={{ color: "var(--color-warn)" }}>{a.reruns}↻</span>
      </td>
      <td className="mono">{a.avg_attempts ?? "—"}</td>
      <td className="mono">{a.verdicts.PASS}/{a.verdicts.WARN}/{a.verdicts.FAIL}</td>
      <td className="text-[12px] text-ink-dim">
        {a.guidance_samples[0] ?? a.reject_reasons[0] ?? <span className="text-ink-faint">—</span>}
      </td>
    </tr>
  );
}

export function InsightsView({ actor }: { actor: string }) {
  const q = useQuery({ queryKey: ["insights"], queryFn: () => api.agentInsights() });

  if (q.isLoading) return <div className="p-6 text-sm text-ink-faint">Loading…</div>;
  const data = q.data;
  if (!data) return <div className="p-6 text-sm text-ink-faint">No data.</div>;

  const s = data.summary;
  const withData = data.agents.filter((a) => a.decided > 0 || a.reruns > 0);

  return (
    <div className="stage">
      <div className="board-head">
        <div className="board-title">Agent Insights</div>
        <div className="board-sub">Human feedback, eval scorecard, operational health &amp; flaky-test intelligence</div>
      </div>
      <p className="mb-4 text-[11px] text-ink-dim">
        Learned from the decisions humans already make — Accept, Reject and Re-run-with-guidance.
        A low trust score means humans frequently override that agent; act on it by tuning its prompt.
      </p>

      <div className="kpi-row">
        {[
          ["Overall acceptance", s.overall_acceptance_rate === null ? "—" : `${Math.round(s.overall_acceptance_rate * 100)}%`],
          ["Accepted", String(s.total_accepted)],
          ["Rejected", String(s.total_rejected)],
          ["Re-runs", String(s.total_reruns)],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 22 }}>{val}</div>
          </div>
        ))}
      </div>

      {data.needs_attention.length > 0 && (
        <div className="referee">
          <div className="referee-kicker">Most human pushback</div>
          <div className="flex flex-wrap gap-2">
            {data.needs_attention.map((a) => (
              <span key={a.agent_key} className="pill pill-warn">
                {a.agent_name} · trust {a.trust_score}
              </span>
            ))}
          </div>
        </div>
      )}

      {withData.length === 0 ? (
        <div className="panel-block text-center text-sm text-ink-faint">
          No human decisions recorded yet. Approve, reject or re-run some agents and this
          fills in.
        </div>
      ) : (
        <div className="panel-block" style={{ padding: 0 }}>
          <div className="dtable" style={{ padding: 20, overflowX: "auto" }}>
            <table style={{ width: "100%" }}>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Trust</th>
                  <th>✓ / ✗ / ↻</th>
                  <th>Avg attempts</th>
                  <th>P/W/F</th>
                  <th>Latest feedback</th>
                </tr>
              </thead>
              <tbody>
                {withData
                  .slice()
                  .sort((a, b) => (a.trust_score ?? 101) - (b.trust_score ?? 101))
                  .map((a) => (
                    <AgentRow key={a.agent_key} a={a} />
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <EvalScorecardSection />
      <OperationalHealth />
      <FlakyIntel actor={actor} />
    </div>
  );
}

/** Eval Scorecard — the golden-dataset harness, live. Every agent with a
 *  golden file, graded now against the demo path. This is the regression
 *  gate: red here means a code change broke a verified, expert-confirmed
 *  expectation. Green means "measured", not "trust me". */
function EvalScorecardSection() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["eval-scorecard"],
    queryFn: () => api.evalScorecard(),
  });
  const data = q.data;
  if (!data) return null;
  const s = data.summary;

  return (
    <div style={{ marginTop: 32 }}>
      <div className="panel-block-title" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: 16, marginBottom: 6 }}>
        Eval Scorecard
      </div>
      <p className="mb-4 text-[11px] text-ink-dim">
        The golden-dataset harness, graded live against the demo path — expert-labelled
        cases, not vibes. Demo-path only today (regression gate for the fixture
        generator); a live-model runner against real Claude is a separate follow-up.
      </p>

      <div className="kpi-row">
        {[
          ["Agent coverage", `${s.agents_with_golden_data}/${s.agents_total} (${s.coverage_percent}%)`],
          ["Total cases", String(s.total_cases)],
          ["Passed", String(s.total_passed)],
          ["Failed", String(s.total_failed)],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 20, color: label === "Failed" && s.total_failed > 0 ? "var(--color-bad)" : undefined }}>
              {val}
            </div>
          </div>
        ))}
      </div>

      {data.agents.length === 0 ? (
        <div className="panel-block text-center text-sm text-ink-faint">No golden datasets yet.</div>
      ) : (
        <div className="panel-block" style={{ padding: 0 }}>
          <div className="dtable" style={{ padding: 20, overflowX: "auto" }}>
            <table style={{ width: "100%" }}>
              <thead>
                <tr><th>Agent</th><th>Cases</th><th>Result</th></tr>
              </thead>
              <tbody>
                {data.agents.map((a) => (
                  <>
                    <tr key={a.agent_key}>
                      <td>{a.agent_name}</td>
                      <td className="mono">{a.cases}</td>
                      <td>
                        {a.failed === 0 ? (
                          <span className="font-mono text-[11px]" style={{ color: "var(--color-ok)" }}>
                            ✓ {a.passed}/{a.cases}
                          </span>
                        ) : (
                          <button
                            className="font-mono text-[11px] hover:underline"
                            style={{ color: "var(--color-bad)" }}
                            onClick={() => setExpanded(expanded === a.agent_key ? null : a.agent_key)}
                          >
                            ✗ {a.passed}/{a.cases} — {expanded === a.agent_key ? "hide" : "show"} failures
                          </button>
                        )}
                      </td>
                    </tr>
                    {expanded === a.agent_key && a.failing_cases.map((fc, i) => (
                      <tr key={`${a.agent_key}-fail-${i}`} style={{ background: "var(--crit-soft)" }}>
                        <td colSpan={3} className="text-[11px]">
                          <span className="font-mono" style={{ color: "var(--color-bad)" }}>{fc.case}</span>
                          <ul className="ml-3 mt-1 list-inside list-disc text-ink-dim">
                            {fc.failing_checks.map((c, j) => (
                              <li key={j}>
                                <span className="font-mono text-[10px]">{c.path}</span>: expected{" "}
                                <span className="text-ink">{JSON.stringify(c.expected)}</span>, got{" "}
                                <span style={{ color: "var(--color-bad)" }}>{JSON.stringify(c.actual)}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/** Flaky-Test Intelligence — cross-run failure signatures with flake scores
 *  and an owned, expiring quarantine (no immortal quarantine). */
function FlakyIntel({ actor }: { actor: string }) {
  const [editing, setEditing] = useState<string | null>(null);
  const [owner, setOwner] = useState("");
  const [days, setDays] = useState("14");
  const toast = useToast();
  const queryClient = useQueryClient();
  const q = useQuery({ queryKey: ["flaky-tests"], queryFn: () => api.flakyTests() });

  const done = (msg: string) => {
    toast("ok", msg);
    setEditing(null);
    queryClient.invalidateQueries({ queryKey: ["flaky-tests"] });
  };
  const quarantine = useMutation({
    mutationFn: (s: FlakySig) =>
      api.quarantineFlaky(s.id, actor, owner, parseInt(days, 10) || 14, ""),
    onSuccess: () => done("Signature quarantined — it expires; it doesn't rot."),
    onError: (e: Error) => toast("error", e.message),
  });
  const clear = useMutation({
    mutationFn: (s: FlakySig) => api.clearFlaky(s.id, actor, "cleared from Insights"),
    onSuccess: () => done("Signature cleared."),
    onError: (e: Error) => toast("error", e.message),
  });

  const data = q.data;
  if (!data || data.signatures.length === 0) return null;
  const s = data.summary;

  return (
    <div style={{ marginTop: 32 }}>
      <div className="panel-block-title" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: 16, marginBottom: 6 }}>
        Flaky-Test Intelligence
      </div>
      <p className="mb-4 text-[11px] text-ink-dim">
        Cross-run memory: recurring failure signatures fingerprinted across runs and
        stories. Known flakes are fed back to the Test Execution Analyst and Defect
        Triage as evidence (&ldquo;re-run, not defect&rdquo;). Quarantine requires an owner and an
        expiry.
      </p>

      <div className="kpi-row">
        {[
          ["Signatures", String(s.total)],
          ["High score (≥50)", String(s.high_score)],
          ["Quarantined", String(s.quarantined)],
          ["Expired quarantines", String(s.expired_quarantines)],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 20 }}>{val}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {data.signatures.map((sig) => (
          <div
            key={sig.id}
            className="panel-block"
            style={{ marginBottom: 0, borderColor: sig.quarantine_expired ? "var(--color-bad)" : undefined }}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className="font-mono text-[11px] font-bold"
                style={{ color: sig.flake_score >= 50 ? "var(--color-bad)" : sig.flake_score >= 25 ? "var(--color-warn)" : "var(--color-ink-dim)" }}
              >
                {sig.flake_score}
              </span>
              <span className="card-id">{sig.ref}</span>
              <span className="text-[13px] font-medium text-ink">{sig.test_name}</span>
              <span
                className={`pill ${sig.status === "QUARANTINED" ? "pill-warn" : "pill-slate"}`}
              >
                {sig.status}
              </span>
              {sig.quarantine_expired && <span className="pill pill-crit">Quarantine expired</span>}
              <span className="ml-auto font-mono text-[10px] text-ink-faint">
                seen {sig.occurrences}× · {sig.stories_seen.length} story(ies) ·{" "}
                {sig.flaky_votes} analyst-flaky vote(s)
                {sig.owner && ` · owner ${sig.owner}`}
                {sig.quarantine_expiry && ` · until ${sig.quarantine_expiry.slice(0, 10)}`}
              </span>
            </div>
            {sig.normalized_message && (
              <div className="mt-1.5 font-mono text-[10px] text-ink-faint">
                {sig.normalized_message.slice(0, 160)}
              </div>
            )}
            {sig.status !== "CLEARED" && (
              <div className="mt-2.5 flex flex-wrap items-center gap-2">
                {editing === sig.id ? (
                  <>
                    <input
                      value={owner}
                      onChange={(e) => setOwner(e.target.value)}
                      placeholder="Owner (required)"
                      className="role-select"
                      style={{ width: 180 }}
                    />
                    <input
                      value={days}
                      onChange={(e) => setDays(e.target.value)}
                      placeholder="Days"
                      className="role-select"
                      style={{ width: 70 }}
                    />
                    <button
                      type="button"
                      className="sync-btn"
                      disabled={quarantine.isPending}
                      onClick={() => {
                        if (!actor.trim()) {
                          toast("error", "Enter your name in the header first.");
                          return;
                        }
                        quarantine.mutate(sig);
                      }}
                    >
                      Quarantine
                    </button>
                    <button type="button" className="ghost-btn" onClick={() => setEditing(null)}>
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    {sig.status !== "QUARANTINED" && (
                      <button type="button" className="ghost-btn" onClick={() => { setEditing(sig.id); setOwner(""); }}>
                        &#9208; Quarantine…
                      </button>
                    )}
                    <button type="button" className="ghost-btn" disabled={clear.isPending} onClick={() => clear.mutate(sig)}>
                      &#10003; Clear (fixed)
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Operational (SRE) health of the fleet — failures, latency, token spend and
 *  per-prompt-version reliability. Deterministic aggregation; no model calls. */
function OperationalHealth() {
  const q = useQuery({
    queryKey: ["agent-op-health"],
    queryFn: () => api.agentOpHealth(),
  });
  const data = q.data;
  if (!data || data.agents.length === 0) return null;
  const s = data.summary;
  return (
    <div style={{ marginTop: 32 }}>
      <div className="panel-block-title" style={{ fontFamily: "var(--font-serif)", fontStyle: "italic", fontSize: 16, marginBottom: 6 }}>
        Operational Health
      </div>
      <p className="mb-4 text-[11px] text-ink-dim">
        The SRE layer: failure rates, latency, token spend and reliability per
        prompt version — did the last prompt bump regress?
      </p>

      <div className="kpi-row">
        {[
          ["Executed runs", String(s.total_executed)],
          ["Failed", String(s.total_failed)],
          ["Tokens in", s.total_tokens_in.toLocaleString()],
          ["Tokens out", s.total_tokens_out.toLocaleString()],
        ].map(([label, val]) => (
          <div key={label} className="kpi">
            <div className="kpi-label">{label}</div>
            <div className="kpi-value" style={{ fontSize: 20 }}>{val}</div>
          </div>
        ))}
      </div>

      {data.alerts.length > 0 && (
        <div className="referee" style={{ background: "var(--crit-soft)", borderColor: "var(--crit-soft)", borderLeftColor: "var(--color-bad)" }}>
          <div className="referee-kicker">Alerts</div>
          <ul className="flex flex-col gap-1 text-[12px]" style={{ color: "var(--color-bad)" }}>
            {data.alerts.map((a, i) => (
              <li key={i}>
                <span className="font-mono text-[10px]">[{a.kind}]</span> {a.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel-block" style={{ padding: 0 }}>
        <div className="dtable" style={{ padding: 20, overflowX: "auto" }}>
          <table style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Agent</th>
                <th>Executed</th>
                <th>Failure rate</th>
                <th>Avg / max s</th>
                <th>Tokens (in→out)</th>
                <th>By prompt version</th>
              </tr>
            </thead>
            <tbody>
              {data.agents.map((a) => (
                <tr key={a.agent_key}>
                  <td>
                    <div className="text-ink">{a.agent_name}</div>
                    <div className="font-mono text-[9.5px] text-ink-faint">now {a.current_prompt_version}</div>
                  </td>
                  <td className="mono">{a.executed}</td>
                  <td>
                    <span
                      className="font-mono text-[11px]"
                      style={{
                        color: a.failure_rate >= 0.25 ? "var(--color-bad)" : a.failure_rate > 0 ? "var(--color-warn)" : "var(--color-ok)",
                      }}
                    >
                      {Math.round(a.failure_rate * 100)}%
                    </span>
                  </td>
                  <td className="mono">{a.avg_duration_s ?? "—"} / {a.max_duration_s ?? "—"}</td>
                  <td className="mono">{a.tokens_in.toLocaleString()}→{a.tokens_out.toLocaleString()}</td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {a.versions.map((v) => (
                        <span
                          key={v.version}
                          className={`pill ${v.failure_rate >= 0.25 ? "pill-crit" : "pill-slate"}`}
                        >
                          {v.version}: {v.executed}✓{v.failed > 0 ? ` ${v.failed}✗` : ""}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
