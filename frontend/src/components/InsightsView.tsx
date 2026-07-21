import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { AgentPerf, FlakySig } from "../types";
import { Badge, Button, useToast } from "../ui";

function trustCls(t: number | null): string {
  if (t === null) return "text-ink-faint";
  if (t >= 85) return "text-ok";
  if (t >= 60) return "text-warn";
  return "text-bad";
}

function TrustBar({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-faint">—</span>;
  const cls = value >= 85 ? "bg-ok" : value >= 60 ? "bg-warn" : "bg-bad";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-panel-2">
        <div className={`h-full ${cls}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`font-mono text-[11px] ${trustCls(value)}`}>{value}</span>
    </div>
  );
}

function AgentRow({ a }: { a: AgentPerf }) {
  return (
    <tr className="border-b border-line/50 align-top">
      <td className="py-2 pr-3">
        <div className="text-ink">{a.agent_name}</div>
        <div className="text-[10px] uppercase tracking-wider text-ink-faint">{a.phase}</div>
      </td>
      <td className="py-2 pr-3">
        <TrustBar value={a.trust_score} />
      </td>
      <td className="py-2 pr-3 font-mono text-[11px]">
        <span className="text-ok">{a.accepted}✓</span>{" "}
        <span className="text-bad">{a.rejected}✗</span>{" "}
        <span className="text-warn">{a.reruns}↻</span>
      </td>
      <td className="py-2 pr-3 font-mono text-[11px] text-ink-dim">
        {a.avg_attempts ?? "—"}
      </td>
      <td className="py-2 pr-3 font-mono text-[10px] text-ink-faint">
        {a.verdicts.PASS}/{a.verdicts.WARN}/{a.verdicts.FAIL}
      </td>
      <td className="py-2 text-[11px] text-ink-dim">
        {a.guidance_samples[0] ?? a.reject_reasons[0] ?? (
          <span className="text-ink-faint">—</span>
        )}
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
    <div className="mx-auto max-w-5xl p-6">
      <h2 className="mb-1 text-sm font-semibold text-ink">Agent Performance & Human Feedback</h2>
      <p className="mb-4 text-[11px] text-ink-dim">
        Learned from the decisions humans already make — Accept, Reject and Re-run-with-guidance.
        A low trust score means humans frequently override that agent; act on it by tuning its prompt.
      </p>

      <div className="mb-5 grid grid-cols-4 gap-3">
        {[
          ["Overall acceptance", s.overall_acceptance_rate === null ? "—" : `${Math.round(s.overall_acceptance_rate * 100)}%`],
          ["Accepted", String(s.total_accepted)],
          ["Rejected", String(s.total_rejected)],
          ["Re-runs", String(s.total_reruns)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {data.needs_attention.length > 0 && (
        <div className="mb-5 rounded-lg border border-warn/40 bg-warn/5 p-3">
          <h3 className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-warn">
            Most human pushback
          </h3>
          <div className="flex flex-wrap gap-2">
            {data.needs_attention.map((a) => (
              <Badge key={a.agent_key} className="border-warn/40 text-warn">
                {a.agent_name} · trust {a.trust_score}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {withData.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No human decisions recorded yet. Approve, reject or re-run some agents and this
          fills in.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[10px] uppercase tracking-wider text-ink-faint">
                <th className="px-3 py-2 font-medium">Agent</th>
                <th className="px-3 py-2 font-medium">Trust</th>
                <th className="px-3 py-2 font-medium">✓ / ✗ / ↻</th>
                <th className="px-3 py-2 font-medium">Avg attempts</th>
                <th className="px-3 py-2 font-medium">P/W/F</th>
                <th className="px-3 py-2 font-medium">Latest feedback</th>
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
    <div className="mb-8">
      <h2 className="mb-1 text-sm font-semibold text-ink">Eval Scorecard</h2>
      <p className="mb-4 text-[11px] text-ink-dim">
        The golden-dataset harness, graded live against the demo path — expert-labelled
        cases, not vibes. Demo-path only today (regression gate for the fixture
        generator); a live-model runner against real Claude is a separate follow-up.
      </p>

      <div className="mb-4 grid grid-cols-4 gap-3">
        {[
          ["Agent coverage", `${s.agents_with_golden_data}/${s.agents_total} (${s.coverage_percent}%)`],
          ["Total cases", String(s.total_cases)],
          ["Passed", String(s.total_passed)],
          ["Failed", String(s.total_failed)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className={`text-lg font-bold ${label === "Failed" && s.total_failed > 0 ? "text-bad" : "text-ink"}`}>
              {val}
            </div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {data.agents.length === 0 ? (
        <div className="rounded-lg border border-line bg-panel p-6 text-center text-sm text-ink-faint">
          No golden datasets yet.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[10px] uppercase tracking-wider text-ink-faint">
                <th className="px-3 py-2 font-medium">Agent</th>
                <th className="px-3 py-2 font-medium">Cases</th>
                <th className="px-3 py-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {data.agents.map((a) => (
                <>
                  <tr key={a.agent_key} className="border-b border-line/50 align-top">
                    <td className="px-3 py-2 text-ink">{a.agent_name}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-dim">{a.cases}</td>
                    <td className="px-3 py-2">
                      {a.failed === 0 ? (
                        <span className="font-mono text-[11px] text-ok">✓ {a.passed}/{a.cases}</span>
                      ) : (
                        <button
                          className="font-mono text-[11px] text-bad hover:underline"
                          onClick={() => setExpanded(expanded === a.agent_key ? null : a.agent_key)}
                        >
                          ✗ {a.passed}/{a.cases} — {expanded === a.agent_key ? "hide" : "show"} failures
                        </button>
                      )}
                    </td>
                  </tr>
                  {expanded === a.agent_key && a.failing_cases.map((fc, i) => (
                    <tr key={`${a.agent_key}-fail-${i}`} className="border-b border-line/50 bg-bad/5">
                      <td colSpan={3} className="px-3 py-2 text-[11px]">
                        <span className="font-mono text-bad">{fc.case}</span>
                        <ul className="ml-3 mt-1 list-inside list-disc text-ink-dim">
                          {fc.failing_checks.map((c, j) => (
                            <li key={j}>
                              <span className="font-mono text-[10px]">{c.path}</span>: expected{" "}
                              <span className="text-ink">{JSON.stringify(c.expected)}</span>, got{" "}
                              <span className="text-bad">{JSON.stringify(c.actual)}</span>
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
    <div className="mt-8">
      <h2 className="mb-1 text-sm font-semibold text-ink">Flaky-Test Intelligence</h2>
      <p className="mb-4 text-[11px] text-ink-dim">
        Cross-run memory: recurring failure signatures fingerprinted across runs and
        stories. Known flakes are fed back to the Test Execution Analyst and Defect
        Triage as evidence (“re-run, not defect”). Quarantine requires an owner and an
        expiry.
      </p>

      <div className="mb-4 grid grid-cols-4 gap-3">
        {[
          ["Signatures", String(s.total)],
          ["High score (≥50)", String(s.high_score)],
          ["Quarantined", String(s.quarantined)],
          ["Expired quarantines", String(s.expired_quarantines)],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {data.signatures.map((sig) => (
          <div
            key={sig.id}
            className={`rounded-lg border bg-panel p-3 ${
              sig.quarantine_expired ? "border-bad/60" : "border-line"
            }`}
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`font-mono text-[11px] font-bold ${
                  sig.flake_score >= 50 ? "text-bad" : sig.flake_score >= 25 ? "text-warn" : "text-ink-dim"
                }`}
              >
                {sig.flake_score}
              </span>
              <span className="font-mono text-[10px] text-accent">{sig.ref}</span>
              <span className="text-xs font-medium text-ink">{sig.test_name}</span>
              <Badge
                className={
                  sig.status === "QUARANTINED"
                    ? "border-warn/50 bg-warn/10 text-warn"
                    : sig.status === "CLEARED"
                      ? "border-line text-ink-faint"
                      : "border-line text-ink-dim"
                }
              >
                {sig.status}
              </Badge>
              {sig.quarantine_expired && (
                <Badge className="border-bad/70 bg-bad/20 font-bold text-bad">
                  QUARANTINE EXPIRED — review
                </Badge>
              )}
              <span className="ml-auto font-mono text-[10px] text-ink-faint">
                seen {sig.occurrences}× · {sig.stories_seen.length} story(ies) ·{" "}
                {sig.flaky_votes} analyst-flaky vote(s)
                {sig.owner && ` · owner ${sig.owner}`}
                {sig.quarantine_expiry && ` · until ${sig.quarantine_expiry.slice(0, 10)}`}
              </span>
            </div>
            {sig.normalized_message && (
              <div className="mt-1 font-mono text-[10px] text-ink-faint">
                {sig.normalized_message.slice(0, 160)}
              </div>
            )}
            {sig.status !== "CLEARED" && (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {editing === sig.id ? (
                  <>
                    <input
                      value={owner}
                      onChange={(e) => setOwner(e.target.value)}
                      placeholder="Owner (required)"
                      className="w-44 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
                    />
                    <input
                      value={days}
                      onChange={(e) => setDays(e.target.value)}
                      placeholder="Days"
                      className="w-16 rounded border border-line bg-bg px-2 py-1 text-[11px] text-ink"
                    />
                    <Button
                      variant="primary"
                      busy={quarantine.isPending}
                      onClick={() => {
                        if (!actor.trim()) {
                          toast("error", "Enter your name in the header first.");
                          return;
                        }
                        quarantine.mutate(sig);
                      }}
                    >
                      Quarantine
                    </Button>
                    <Button variant="ghost" onClick={() => setEditing(null)}>
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    {sig.status !== "QUARANTINED" && (
                      <Button onClick={() => { setEditing(sig.id); setOwner(""); }}>
                        ⏸ Quarantine…
                      </Button>
                    )}
                    <Button variant="ghost" busy={clear.isPending} onClick={() => clear.mutate(sig)}>
                      ✓ Clear (fixed)
                    </Button>
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
    <div className="mt-8">
      <h2 className="mb-1 text-sm font-semibold text-ink">Operational Health</h2>
      <p className="mb-4 text-[11px] text-ink-dim">
        The SRE layer: failure rates, latency, token spend and reliability per
        prompt version — did the last prompt bump regress?
      </p>

      <div className="mb-4 grid grid-cols-4 gap-3">
        {[
          ["Executed runs", String(s.total_executed)],
          ["Failed", String(s.total_failed)],
          ["Tokens in", s.total_tokens_in.toLocaleString()],
          ["Tokens out", s.total_tokens_out.toLocaleString()],
        ].map(([label, val]) => (
          <div key={label} className="rounded-lg border border-line bg-panel p-3">
            <div className="text-lg font-bold text-ink">{val}</div>
            <div className="text-[10px] uppercase tracking-wider text-ink-faint">{label}</div>
          </div>
        ))}
      </div>

      {data.alerts.length > 0 && (
        <div className="mb-4 rounded-lg border border-bad/40 bg-bad/5 p-3">
          <h3 className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-bad">
            Alerts
          </h3>
          <ul className="flex flex-col gap-1 text-[11px] text-bad">
            {data.alerts.map((a, i) => (
              <li key={i}>
                <span className="font-mono text-[10px]">[{a.kind}]</span> {a.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-line bg-panel">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-line text-[10px] uppercase tracking-wider text-ink-faint">
              <th className="px-3 py-2 font-medium">Agent</th>
              <th className="px-3 py-2 font-medium">Executed</th>
              <th className="px-3 py-2 font-medium">Failure rate</th>
              <th className="px-3 py-2 font-medium">Avg / max s</th>
              <th className="px-3 py-2 font-medium">Tokens (in→out)</th>
              <th className="px-3 py-2 font-medium">By prompt version</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((a) => (
              <tr key={a.agent_key} className="border-b border-line/50 align-top">
                <td className="px-3 py-2">
                  <div className="text-ink">{a.agent_name}</div>
                  <div className="font-mono text-[10px] text-ink-faint">
                    now {a.current_prompt_version}
                  </div>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-ink-dim">
                  {a.executed}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`font-mono text-[11px] ${
                      a.failure_rate >= 0.25
                        ? "text-bad"
                        : a.failure_rate > 0
                          ? "text-warn"
                          : "text-ok"
                    }`}
                  >
                    {Math.round(a.failure_rate * 100)}%
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-ink-dim">
                  {a.avg_duration_s ?? "—"} / {a.max_duration_s ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-[11px] text-ink-dim">
                  {a.tokens_in.toLocaleString()}→{a.tokens_out.toLocaleString()}
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {a.versions.map((v) => (
                      <Badge
                        key={v.version}
                        className={
                          v.failure_rate >= 0.25
                            ? "border-bad/50 bg-bad/10 text-bad"
                            : "border-line text-ink-dim"
                        }
                      >
                        {v.version}: {v.executed}✓{v.failed > 0 ? ` ${v.failed}✗` : ""}
                      </Badge>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
