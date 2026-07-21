import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { RiskEntry } from "../types";
import { useToast } from "../ui";

/** Risk Acceptance Register — the quality-debt ledger. Every knowingly-
 *  accepted risk (run accepted despite findings, gate signed over WARNs,
 *  CONDITIONAL_GO) as a managed position: owner, rationale, severity-derived
 *  review-by date, OPEN → REVIEWED → CLOSED. Overdue entries escalate red. */

const SEV_PILL: Record<string, string> = {
  BLOCKER: "pill-crit",
  CRITICAL: "pill-crit",
  HIGH: "pill-crit",
  MEDIUM: "pill-warn",
  LOW: "pill-slate",
};
const STATUS_PILL: Record<string, string> = {
  CLOSED: "pill-slate",
  REVIEWED: "pill-good",
  OPEN: "pill-warn",
};

const SOURCE_LABEL: Record<string, string> = {
  RUN_ACCEPTED_WITH_FINDINGS: "run accepted despite findings",
  GATE_SIGNED_OVER_WARN: "gate signed over WARN",
  CONDITIONAL_GO: "conditional go",
};

export function RiskRegisterView({ actor }: { actor: string }) {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [action, setAction] = useState<{ entry: RiskEntry; kind: "review" | "close" } | null>(null);
  const [note, setNote] = useState("");
  const toast = useToast();
  const queryClient = useQueryClient();

  const q = useQuery({
    queryKey: ["risk-register"],
    queryFn: () => api.riskRegister(),
  });

  const act = useMutation({
    mutationFn: () =>
      action!.kind === "review"
        ? api.reviewRisk(action!.entry.id, actor, note)
        : api.closeRisk(action!.entry.id, actor, note),
    onSuccess: () => {
      toast("ok", action!.kind === "review"
        ? "Risk re-affirmed — review window restarted."
        : "Risk closed.");
      setAction(null);
      setNote("");
      queryClient.invalidateQueries({ queryKey: ["risk-register"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const data = q.data;
  if (q.isLoading) return <div className="p-6 text-sm text-ink-faint">Loading…</div>;
  if (!data) return <div className="p-6 text-sm text-ink-faint">No data.</div>;

  const entries = statusFilter
    ? data.entries.filter((e) => e.status === statusFilter)
    : data.entries;
  const s = data.summary;

  return (
    <div className="stage">
      <div className="board-head">
        <div className="board-title">Risk Acceptance Register</div>
        <div className="board-sub">
          Every knowingly-accepted risk — sign-offs are managed positions, not terminal events
        </div>
      </div>

      <div className="kpi-row">
        <div className="kpi">
          <div className="kpi-label">Total entries</div>
          <div className="kpi-value">{s.total}</div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Open</div>
          <div className="kpi-value" style={{ color: s.open > 0 ? "var(--color-warn)" : undefined }}>
            {s.open}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Overdue for review</div>
          <div className="kpi-value" style={{ color: s.overdue > 0 ? "var(--color-bad)" : undefined }}>
            {s.overdue}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-label">Open by severity</div>
          <div className="kpi-value" style={{ fontSize: 15 }}>
            {Object.entries(s.by_severity).map(([k, v]) => `${k[0]}:${v}`).join(" ") || "—"}
          </div>
        </div>
      </div>

      <div className="navlinks" style={{ marginBottom: 14 }}>
        {["", "OPEN", "REVIEWED", "CLOSED"].map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setStatusFilter(f)}
            className={statusFilter === f ? "active" : ""}
          >
            {f || "All"}
          </button>
        ))}
      </div>

      {entries.length === 0 ? (
        <div className="panel-block text-center text-sm text-ink-faint">
          No accepted risks on record — nothing has been signed over findings.
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {entries.map((e) => (
            <div
              key={e.id}
              className="panel-block"
              style={{ marginBottom: 0, borderColor: e.overdue ? "var(--color-bad)" : undefined }}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={`pill ${SEV_PILL[e.severity] ?? "pill-slate"}`}>{e.severity}</span>
                <span className="card-id">{e.jira_key}</span>
                <span className="text-[13px] font-medium text-ink">{e.title}</span>
                {e.overdue && <span className="pill pill-crit">OVERDUE</span>}
                <span className={`pill ${STATUS_PILL[e.status] ?? "pill-slate"}`}>{e.status}</span>
                <span className="ml-auto font-mono text-[10px] text-ink-faint">
                  {SOURCE_LABEL[e.source] ?? e.source} · review by{" "}
                  {(e.review_by ?? "").slice(0, 10)}
                </span>
              </div>
              {e.detail && <div className="mt-1.5 text-[12px] text-ink-dim">{e.detail}</div>}
              <div className="mt-1.5 font-mono text-[10.5px] text-ink-faint">
                Accepted by <b style={{ color: "var(--color-ink)" }}>{e.accepted_by}</b>
                {e.rationale && <> — &ldquo;{e.rationale}&rdquo;</>}
                {e.reviewed_by && (
                  <> · re-affirmed by {e.reviewed_by} {e.review_note && `("${e.review_note}")`}</>
                )}
                {e.closed_by && (
                  <> · closed by {e.closed_by} {e.closure_note && `("${e.closure_note}")`}</>
                )}
              </div>

              {e.status !== "CLOSED" && (
                <div className="mt-2.5 flex gap-2">
                  {action?.entry.id === e.id ? (
                    <div className="flex w-full flex-wrap items-center gap-2">
                      <input
                        value={note}
                        onChange={(ev) => setNote(ev.target.value)}
                        placeholder={
                          action.kind === "review"
                            ? "Why is this still acceptable?"
                            : "Why does this risk no longer exist?"
                        }
                        className="role-select"
                        style={{ minWidth: 280, flex: 1 }}
                      />
                      <button
                        type="button"
                        className="sync-btn"
                        disabled={act.isPending}
                        onClick={() => {
                          if (!actor.trim()) {
                            toast("error", "Enter your name in the header first.");
                            return;
                          }
                          act.mutate();
                        }}
                      >
                        {action.kind === "review" ? "Re-affirm" : "Close risk"}
                      </button>
                      <button type="button" className="ghost-btn" onClick={() => setAction(null)}>
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        type="button"
                        className="ghost-btn"
                        onClick={() => { setAction({ entry: e, kind: "review" }); setNote(""); }}
                      >
                        &#8635; Review (re-affirm)
                      </button>
                      <button
                        type="button"
                        className="ghost-btn"
                        onClick={() => { setAction({ entry: e, kind: "close" }); setNote(""); }}
                      >
                        &#10003; Close…
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
