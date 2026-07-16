import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import type { AgentPerf } from "../types";
import { Badge } from "../ui";

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

export function InsightsView() {
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
    </div>
  );
}
