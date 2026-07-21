import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api } from "../api";
import type { AgentDef, Gate, Phase, Run, StoryHealth } from "../types";
import { PHASES } from "../types";
import { fmtTime, useToast } from "../ui";
import { ArtifactsPanel } from "./ArtifactsPanel";
import { GateModal } from "./GateModal";
import { PipelineGraph } from "./PipelineGraph";
import { RunCard } from "./RunCard";

type DrawerTab = "runs" | "pipeline" | "gates" | "artifacts" | "timeline" | "details";

const PHASE_SHORT: Record<Phase, string> = {
  REFINEMENT: "Refinement",
  DEVELOPMENT: "Development",
  TESTING: "Testing",
  RELEASE: "Release",
};
const FCA_TIER: Record<string, string> = { HIGH: "high", MEDIUM: "med", LOW: "low" };

const EVENT_ICONS: Record<string, string> = {
  RUN_PROPOSED: "○",
  RUN_UNLOCKED: "◌",
  RUN_APPROVED: "▶",
  RUN_COMPLETED: "◉",
  RUN_ACCEPTED: "✓",
  RUN_REJECTED: "✗",
  RUN_RERUN_REQUESTED: "↻",
  RUN_FAILED: "⚠",
  GATE_READY: "◇",
  GATE_SIGNED_OFF: "✒",
  GATE_REJECTED: "✗",
  GATE_BLOCKED: "⛔",
  PHASE_ADVANCED: "»",
  STORY_RELEASED: "★",
  STORY_SYNCED: "⟳",
  STORY_OUT_OF_SCOPE: "−",
  PUSH_DRAFTED: "✎",
  PUSH_APPROVED: "☑",
  PUSH_SENT: "↗",
  PUSH_FAILED: "⚠",
  PUSH_RETRIED: "↻",
};
const TL_DOT: Record<string, string> = {
  RUN_REJECTED: "bad",
  RUN_FAILED: "bad",
  GATE_REJECTED: "bad",
  GATE_BLOCKED: "bad",
  RUN_RERUN_REQUESTED: "warn",
  STORY_OUT_OF_SCOPE: "slate",
  RUN_PROPOSED: "slate",
};

const BAND_LABEL: Record<string, string> = {
  HEALTHY: "Healthy",
  AT_RISK: "At risk",
  CRITICAL: "Critical",
  BLOCKED: "Blocked",
  NO_DATA: "No data",
};
const BAND_COLOR: Record<string, string> = {
  HEALTHY: "var(--color-ok)",
  AT_RISK: "var(--color-warn)",
  CRITICAL: "var(--color-bad)",
  BLOCKED: "var(--color-bad)",
  NO_DATA: "var(--color-ink-faint)",
};
const SEV_COLOR: Record<string, string> = {
  HIGH: "var(--color-bad)",
  MEDIUM: "var(--color-warn)",
  LOW: "var(--color-ink-dim)",
};

function HealthCard({ health }: { health: StoryHealth }) {
  const label = BAND_LABEL[health.band] ?? "No data";
  const color = BAND_COLOR[health.band] ?? BAND_COLOR.NO_DATA;
  const score = health.score ?? 0;
  const needleAngle = -90 + (Math.max(0, Math.min(100, score)) / 100) * 180;

  return (
    <div className="detail-body" style={{ padding: 0 }}>
      <div className="health">
        <div className="section-label" style={{ alignSelf: "flex-start" }}>
          Release Health
        </div>
        <div className="gauge">
          <div className="gauge-dial">
            <div className="gauge-track" />
          </div>
          <div className="gauge-needle" style={{ "--needle-angle": `${needleAngle}deg` } as CSSProperties} />
          <div className="gauge-hub" />
        </div>
        <div className="health-score">
          {score}
          <sup>/100</sup>
        </div>
        <div className="health-label" style={{ color }}>
          &#9679; {label}
        </div>
        <div className="health-meta">
          {health.agents_evaluated} agents &middot; assurance {health.assurance ?? "—"}
          <br />
          {health.counts.pass} &#10003; passed &middot; {health.counts.warn} &#9650; flagged &middot;{" "}
          {health.counts.fail} &#10007; blocked
          {health.worst_finding_severity && <>
            <br />worst finding: {health.worst_finding_severity}
          </>}
        </div>
      </div>

      <div>
        {health.blockers.length > 0 && (
          <div className="referee" style={{ borderLeftColor: "var(--color-bad)", background: "var(--crit-soft)", borderColor: "var(--crit-soft)" }}>
            <div className="referee-kicker">Release blocked</div>
            <p style={{ margin: 0 }}>
              &#9940; {health.blockers.length} release-blocker(s): {health.blockers.map((b) => b.agent).join(", ")}
            </p>
          </div>
        )}

        {health.inconsistencies.map((inc, i) => (
          <div key={i} className="referee">
            <div className="referee-kicker">
              Cross-agent referee &middot; {health.inconsistency_count} inconsistenc{health.inconsistency_count === 1 ? "y" : "ies"}
            </div>
            <div className="referee-title">
              <b style={{ color: SEV_COLOR[inc.severity] ?? SEV_COLOR.MEDIUM }}>{inc.severity}</b>{" "}
              &nbsp;{inc.agents.join(" ⇄ ")}
            </div>
            <p>{inc.detail}</p>
            <div className="action">▸ {inc.recommendation}</div>
          </div>
        ))}

        {health.least_confident.length > 0 && (
          <div className="section-label" style={{ marginTop: 4 }}>
            Least confident: {health.least_confident.map((l) => `${l.agent} (${l.verdict})`).join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

export function StoryDrawer({
  storyId,
  actor,
  agents,
  onClose,
  initialTab = "runs",
  autoOpenGateId,
}: {
  storyId: string;
  actor: string;
  agents: Map<string, AgentDef>;
  onClose: () => void;
  initialTab?: DrawerTab;
  autoOpenGateId?: string;
}) {
  const [tab, setTab] = useState<DrawerTab>(initialTab);
  const [gateModal, setGateModal] = useState<Gate | null>(null);
  const [pendingAgent, setPendingAgent] = useState<string | null>(null);
  const autoOpenedRef = useRef(false);
  const toast = useToast();
  const queryClient = useQueryClient();

  const storyQuery = useQuery({
    queryKey: ["story", storyId],
    queryFn: () => api.story(storyId),
  });
  const timelineQuery = useQuery({
    queryKey: ["timeline", storyId],
    queryFn: () => api.timeline(storyId),
    enabled: tab === "timeline",
  });
  const healthQuery = useQuery({
    queryKey: ["health", storyId],
    queryFn: () => api.health(storyId),
    enabled: tab === "runs",
  });

  const refreshMutation = useMutation({
    mutationFn: () => api.refreshStory(storyId),
    onSuccess: () => {
      toast("ok", "Story re-pulled from Jira");
      queryClient.invalidateQueries({ queryKey: ["story", storyId] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const story = storyQuery.data;

  // Pipeline-graph click-through: switch to the runs tab, then scroll to the
  // selected agent's run card once it has rendered.
  useEffect(() => {
    if (tab !== "runs" || !pendingAgent) return;
    const key = pendingAgent;
    setPendingAgent(null);
    requestAnimationFrame(() => {
      document
        .getElementById(`agent-${key}`)
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, [tab, pendingAgent]);

  // Deep-link from the work queue: once loaded, jump straight to the gate
  // sign-off ceremony (only the first time — don't re-open on refetch).
  useEffect(() => {
    if (!autoOpenGateId || !story || autoOpenedRef.current) return;
    const gate = story.gates.find((g) => g.id === autoOpenGateId);
    if (gate) {
      autoOpenedRef.current = true;
      setGateModal(gate);
    }
  }, [autoOpenGateId, story]);

  const runsByAgent = useMemo(() => {
    const map = new Map<string, Run[]>();
    for (const run of story?.runs ?? []) {
      const list = map.get(run.agent_key) ?? [];
      list.push(run);
      map.set(run.agent_key, list);
    }
    for (const list of map.values()) list.sort((a, b) => a.attempt - b.attempt);
    return map;
  }, [story?.runs]);

  const requireActor = () => {
    if (!actor.trim()) {
      toast("error", "Enter your name in the header first — every action is attributed.");
      return false;
    }
    return true;
  };

  const TABS: [DrawerTab, string][] = [
    ["runs", "Agent Runs"],
    ["pipeline", "Pipeline"],
    ["gates", "Gates"],
    ["artifacts", "Artifacts"],
    ["timeline", "Timeline"],
    ["details", "Story"],
  ];

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div
        className="detail flex h-full w-full max-w-[780px] flex-col"
        style={{ borderRadius: 0, borderLeft: "1px solid var(--line-strong)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {!story ? (
          <div className="flex flex-1 items-center justify-center text-sm text-ink-faint">
            Loading…
          </div>
        ) : (
          <>
            <div className="detail-head">
              <div>
                <div className="detail-head-l">
                  <span className="card-id" style={{ fontSize: 14 }}>{story.jira_key}</span>
                  {story.cloud && <span className="chip">{story.cloud}</span>}
                  {story.fca_impact && (
                    <span className={`chip tier-${FCA_TIER[story.fca_impact] ?? "low"}`}>
                      FCA {story.fca_impact}
                      {!story.fca_impact_confirmed && " (unconfirmed)"}
                    </span>
                  )}
                  <span className="chip stage">{PHASE_SHORT[story.current_phase]}</span>
                </div>
                <h1 className="detail-title">{story.summary}</h1>
                {story.changed_since_agent_run && (
                  <p className="mt-2 font-mono text-[11px]" style={{ color: "var(--color-warn)" }}>
                    &#9888; This story changed in Jira after agents ran. Review the outputs and
                    consider a re-run — approval history is preserved either way.
                  </p>
                )}
              </div>
              <div className="detail-head-r">
                <button
                  type="button"
                  className="ghost-btn"
                  title="Open the FCA-ready Regulatory Evidence Pack (print to PDF)"
                  onClick={() => window.open(`/api/v1/stories/${storyId}/evidence-pack`, "_blank")}
                >
                  &#10552; Evidence Pack
                </button>
                <button
                  type="button"
                  className="ghost-btn"
                  title="Re-pull this story from Jira"
                  disabled={refreshMutation.isPending}
                  onClick={() => refreshMutation.mutate()}
                >
                  &#8635; Refresh
                </button>
                <button type="button" className="ghost-btn" onClick={onClose}>
                  &#10005;
                </button>
              </div>
            </div>

            <div className="tabs">
              {TABS.map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setTab(id)}
                  className={tab === id ? "tab-btn active" : "tab-btn"}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto">
              {tab === "runs" && (
                <div className="flex flex-col gap-5 tab-pad">
                  {healthQuery.data && healthQuery.data.score !== null && (
                    <HealthCard health={healthQuery.data} />
                  )}
                  {PHASES.map((phase) => {
                    const phaseAgents = Array.from(agents.values())
                      .filter((a) => a.phase === phase)
                      .sort((a, b) => a.sequence - b.sequence);
                    const anyRun = phaseAgents.some((a) => runsByAgent.has(a.key));
                    if (!anyRun) return null;
                    return (
                      <section key={phase}>
                        <div className="section-label">{PHASE_SHORT[phase]}</div>
                        <div className="flex flex-col gap-2">
                          {phaseAgents.map((agentDef) => {
                            const attempts = runsByAgent.get(agentDef.key) ?? [];
                            if (attempts.length === 0) return null;
                            return (
                              <div
                                key={agentDef.key}
                                id={`agent-${agentDef.key}`}
                                className="flex scroll-mt-2 flex-col gap-2"
                              >
                                {attempts.map((run) => (
                                  <RunCard
                                    key={run.id}
                                    run={run}
                                    parent={
                                      run.parent_run_id
                                        ? attempts.find((r) => r.id === run.parent_run_id) ?? null
                                        : null
                                    }
                                    agent={agentDef}
                                    actor={actor}
                                    requireActor={requireActor}
                                  />
                                ))}
                              </div>
                            );
                          })}
                        </div>
                      </section>
                    );
                  })}
                </div>
              )}

              {tab === "pipeline" && (
                <div className="flex flex-col gap-2 tab-pad">
                  <p className="text-[11px] text-ink-dim">
                    The story's agent pipeline: chained inputs flow left to
                    right through the four HITL gates. Click any agent to open
                    its run.
                  </p>
                  <PipelineGraph
                    storyId={storyId}
                    onSelectAgent={(key) => {
                      setPendingAgent(key);
                      setTab("runs");
                    }}
                  />
                </div>
              )}

              {tab === "gates" && (
                <div className="tab-pad">
                  <div className="ledger" style={{ marginBottom: 16 }}>
                    {story.gates
                      .slice()
                      .sort((a, b) => PHASES.indexOf(a.phase) - PHASES.indexOf(b.phase))
                      .map((gate, idx) => {
                        const passed = gate.status === "SIGNED_OFF";
                        const flagged = gate.status === "READY_FOR_SIGNOFF" || gate.status === "REJECTED";
                        return (
                          <div key={gate.id} className="gate-row">
                            <span className={`gate-mark ${passed ? "pass" : flagged ? "flag" : "pending"}`}>
                              G{idx + 1}
                            </span>
                            <div style={{ flex: 1 }}>
                              <div className="gate-text">{PHASE_SHORT[gate.phase]} Sign-Off</div>
                              {gate.approver_name ? (
                                <div className="gate-owner">
                                  {gate.approver_name} ({gate.approver_role}) &middot; {fmtTime(gate.decided_at)}
                                  {gate.rationale && <> — &ldquo;{gate.rationale}&rdquo;</>}
                                </div>
                              ) : (
                                <div className="gate-owner">{gate.status.replaceAll("_", " ").toLowerCase()}</div>
                              )}
                            </div>
                            {gate.status === "READY_FOR_SIGNOFF" && (
                              <button
                                type="button"
                                className="sync-btn"
                                onClick={() => requireActor() && setGateModal(gate)}
                              >
                                &#9990; Open sign-off ceremony
                              </button>
                            )}
                          </div>
                        );
                      })}
                  </div>
                  <p className="text-[10px] leading-relaxed text-ink-faint">
                    Gates unlock strictly in order. A gate becomes ready only when every
                    phase agent's latest run is accepted with no release-blocking
                    findings — FCA-scenario and financial-data-integrity failures cannot
                    be overridden.
                  </p>
                </div>
              )}

              {tab === "artifacts" && (
                <div className="tab-pad">
                  <ArtifactsPanel
                    storyId={storyId}
                    jiraKey={story.jira_key}
                    githubRepo={story.github_repo}
                    githubBranch={story.github_branch}
                    actor={actor}
                  />
                </div>
              )}

              {tab === "timeline" && (
                <div className="tab-pad">
                  <div className="timeline">
                    {(timelineQuery.data ?? []).map((event) => (
                      <div key={event.id} className="tl-row">
                        <span className={`tl-dot ${TL_DOT[event.event_type] ?? ""}`} />
                        <div className="tl-time">
                          {EVENT_ICONS[event.event_type] ?? "·"} {event.actor} &middot; {fmtTime(event.created_at)}
                        </div>
                        <div className="tl-desc">{event.event_type.replaceAll("_", " ")}</div>
                        {typeof event.payload.reason === "string" && (
                          <p className="text-[10.5px] italic text-ink-dim">&ldquo;{event.payload.reason}&rdquo;</p>
                        )}
                        {typeof event.payload.rationale === "string" && (
                          <p className="text-[10.5px] italic text-ink-dim">&ldquo;{event.payload.rationale}&rdquo;</p>
                        )}
                        {typeof event.payload.guidance === "string" && (
                          <p className="text-[10.5px] italic text-review">guidance: &ldquo;{event.payload.guidance}&rdquo;</p>
                        )}
                      </div>
                    ))}
                    {timelineQuery.data?.length === 0 && (
                      <p className="text-xs text-ink-faint">No events yet.</p>
                    )}
                  </div>
                </div>
              )}

              {tab === "details" && (
                <div className="tab-pad">
                  <p className="story-lede">{story.description ?? "No description captured."}</p>

                  <div className="section-label">Acceptance criteria</div>
                  {story.acceptance_criteria.length ? (
                    <ol className="mb-5 flex flex-col gap-1.5 text-ink">
                      {story.acceptance_criteria.map((ac, i) => (
                        <li key={i} className="flex gap-2 text-[13px]">
                          <span className="font-mono text-[10px] text-accent">AC-{i + 1}</span>
                          <span>{ac}</span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mb-5 text-[13px] text-ink-faint">None captured.</p>
                  )}

                  <div className="dtable">
                    <table style={{ width: "100%" }}>
                      <tbody>
                        {(
                          [
                            ["Sprint", story.sprint ?? "—"],
                            ["Jira status", story.jira_status ?? "—"],
                            ["Assignee", story.assignee ?? "—"],
                            ["Priority", story.priority ?? "—"],
                            ["Labels", story.labels.join(", ") || "—"],
                            ["Last synced", fmtTime(story.last_synced_at)],
                            ["Jira updated", fmtTime(story.jira_updated_at)],
                          ] as [string, string][]
                        ).map(([k, v]) => (
                          <tr key={k}>
                            <td className="mono" style={{ width: 140 }}>{k}</td>
                            <td>{v}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {gateModal && story && (
        <GateModal
          gate={gateModal}
          story={story}
          agents={agents}
          actor={actor}
          onClose={() => setGateModal(null)}
        />
      )}
    </div>
  );
}
