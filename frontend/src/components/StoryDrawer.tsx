import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api } from "../api";
import type { AgentDef, Gate, Phase, Run, StoryHealth } from "../types";
import { PHASES } from "../types";
import {
  Badge,
  Button,
  fmtTime,
  GATE_STATUS_META,
  useToast,
} from "../ui";
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

const BAND_META: Record<string, { label: string; cls: string; ring: string }> = {
  HEALTHY: { label: "Healthy", cls: "text-ok", ring: "border-ok/50 bg-ok/10" },
  AT_RISK: { label: "At risk", cls: "text-warn", ring: "border-warn/50 bg-warn/10" },
  CRITICAL: { label: "Critical", cls: "text-bad", ring: "border-bad/50 bg-bad/10" },
  BLOCKED: { label: "Blocked", cls: "text-bad", ring: "border-bad/60 bg-bad/15" },
  NO_DATA: { label: "No data", cls: "text-ink-faint", ring: "border-line" },
};
const SEV_CLS: Record<string, string> = {
  HIGH: "border-bad/50 bg-bad/10 text-bad",
  MEDIUM: "border-warn/50 bg-warn/10 text-warn",
  LOW: "border-line text-ink-dim",
};

function HealthCard({ health }: { health: StoryHealth }) {
  const band = BAND_META[health.band] ?? BAND_META.NO_DATA;
  const score = health.score ?? 0;
  const needleAngle = -90 + (Math.max(0, Math.min(100, score)) / 100) * 180;
  return (
    <section className={`rounded-lg border p-3 ${band.ring}`}>
      <div className="flex items-center gap-4">
        <div className="flex flex-col items-center">
          <div className="dial">
            <div className="dial-ring" />
            <div className="dial-needle" style={{ "--needle-angle": `${needleAngle}deg` } as CSSProperties} />
            <div className="dial-pivot" />
          </div>
          <div className={`font-serif text-xl font-semibold ${band.cls}`}>
            {score}
            <span className="font-mono text-xs text-ink-faint">/100</span>
          </div>
        </div>
        <div className="flex flex-col">
          <span className={`font-serif text-sm font-semibold italic ${band.cls}`}>
            Release Health · {band.label}
          </span>
          <span className="text-[10px] text-ink-faint">
            {health.agents_evaluated} agents · assurance {health.assurance ?? "—"} ·{" "}
            {health.counts.pass}✓ {health.counts.warn}▲ {health.counts.fail}✗
            {health.worst_finding_severity && (
              <> · worst finding {health.worst_finding_severity}</>
            )}
          </span>
        </div>
        <div className="ml-auto flex gap-1">
          {health.phase_breakdown.map((p) => (
            <div key={p.phase} className="text-center" title={`${p.phase}: ${p.score}`}>
              <div className="font-mono text-[11px] text-ink">{p.score}</div>
              <div className="text-[8px] uppercase text-ink-faint">{p.phase.slice(0, 3)}</div>
            </div>
          ))}
        </div>
      </div>

      {health.blockers.length > 0 && (
        <div className="mt-2 rounded border border-bad/40 bg-bad/5 px-2 py-1.5 text-[11px] text-bad">
          ⛔ {health.blockers.length} release-blocker(s):{" "}
          {health.blockers.map((b) => b.agent).join(", ")}
        </div>
      )}

      {health.inconsistencies.length > 0 && (
        <div className="mt-2">
          <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Cross-agent referee · {health.inconsistency_count} inconsistency(ies)
          </h4>
          <ul className="flex flex-col gap-1.5">
            {health.inconsistencies.map((inc, i) => (
              <li key={i} className="rounded border border-line bg-bg/50 p-2">
                <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                  <Badge className={SEV_CLS[inc.severity] ?? "border-line text-ink-dim"}>
                    {inc.severity}
                  </Badge>
                  <span className="font-mono text-[10px] text-accent">{inc.agents.join(" ⇄ ")}</span>
                </div>
                <div className="text-[11px] text-ink">{inc.detail}</div>
                <div className="mt-0.5 text-[10px] text-ink-dim">▸ {inc.recommendation}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {health.least_confident.length > 0 && (
        <div className="mt-2 text-[10px] text-ink-faint">
          Least confident: {health.least_confident.map((l) => `${l.agent} (${l.verdict})`).join(", ")}
        </div>
      )}
    </section>
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

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-[760px] flex-col border-l border-line bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {!story ? (
          <div className="flex flex-1 items-center justify-center text-sm text-ink-faint">
            Loading…
          </div>
        ) : (
          <>
            {/* header */}
            <div className="border-b border-line px-5 py-4">
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-accent">
                  {story.jira_key}
                </span>
                {story.cloud && <Badge className="border-line text-ink-dim">{story.cloud}</Badge>}
                {story.fca_impact && (
                  <Badge
                    className={
                      story.fca_impact === "HIGH"
                        ? "border-bad/50 bg-bad/10 text-bad"
                        : "border-warn/50 bg-warn/10 text-warn"
                    }
                  >
                    FCA {story.fca_impact}
                    {!story.fca_impact_confirmed && " (unconfirmed)"}
                  </Badge>
                )}
                <Badge className="border-accent/40 text-accent">
                  {PHASE_SHORT[story.current_phase]}
                </Badge>
                <div className="ml-auto flex items-center gap-2">
                  <Button
                    variant="ghost"
                    title="Open the FCA-ready Regulatory Evidence Pack (print to PDF)"
                    onClick={() =>
                      window.open(`/api/v1/stories/${storyId}/evidence-pack`, "_blank")
                    }
                  >
                    ⧉ Evidence Pack
                  </Button>
                  <Button
                    variant="ghost"
                    title="Re-pull this story from Jira"
                    busy={refreshMutation.isPending}
                    onClick={() => refreshMutation.mutate()}
                  >
                    ⟳ Refresh
                  </Button>
                  <Button variant="ghost" onClick={onClose}>
                    ✕
                  </Button>
                </div>
              </div>
              <h1 className="mt-2 font-serif text-base italic leading-snug text-ink">
                {story.summary}
              </h1>
              {story.changed_since_agent_run && (
                <div className="mt-2 rounded border border-warn/40 bg-warn/10 px-2.5 py-1.5 text-[11px] text-warn">
                  ⚠ This story changed in Jira after agents ran. Review the outputs and
                  consider a re-run — approval history is preserved either way.
                </div>
              )}

              <nav className="mt-3 flex gap-1">
                {(
                  [
                    ["runs", "Agent Runs"],
                    ["pipeline", "Pipeline"],
                    ["gates", "Gates"],
                    ["artifacts", "Artifacts"],
                    ["timeline", "Timeline"],
                    ["details", "Story"],
                  ] as [DrawerTab, string][]
                ).map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => setTab(id)}
                    className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      tab === id
                        ? "bg-accent/15 text-accent"
                        : "text-ink-dim hover:bg-panel-2"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </nav>
            </div>

            {/* body */}
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {tab === "runs" && (
                <div className="flex flex-col gap-5">
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
                        <h3 className="mb-2 text-[10px] font-bold uppercase tracking-[0.15em] text-ink-faint">
                          {PHASE_SHORT[phase]}
                        </h3>
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
                <div className="flex flex-col gap-2">
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
                <div className="flex flex-col gap-3">
                  {story.gates
                    .slice()
                    .sort((a, b) => PHASES.indexOf(a.phase) - PHASES.indexOf(b.phase))
                    .map((gate, idx) => {
                      const meta = GATE_STATUS_META[gate.status];
                      return (
                        <div
                          key={gate.id}
                          className="rounded-lg border border-line bg-bg/40 px-4 py-3"
                        >
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-xs text-ink-faint">
                              G{idx + 1}
                            </span>
                            <span className="text-xs font-semibold text-ink">
                              {PHASE_SHORT[gate.phase]} Sign-Off
                            </span>
                            <span
                              className={`rounded border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${meta.cls}`}
                            >
                              {meta.label}
                            </span>
                            {gate.status === "READY_FOR_SIGNOFF" && (
                              <Button
                                variant="primary"
                                className="ml-auto"
                                onClick={() => requireActor() && setGateModal(gate)}
                              >
                                ✒ Open sign-off ceremony
                              </Button>
                            )}
                          </div>
                          {gate.approver_name && (
                            <div className="mt-2 text-[11px] leading-relaxed text-ink-dim">
                              <span className="text-ink">{gate.approver_name}</span> (
                              {gate.approver_role}) · {fmtTime(gate.decided_at)}
                              <p className="mt-0.5 italic">“{gate.rationale}”</p>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  <p className="text-[10px] leading-relaxed text-ink-faint">
                    Gates unlock strictly in order. A gate becomes ready only when every
                    phase agent's latest run is accepted with no release-blocking
                    findings — FCA-scenario and financial-data-integrity failures cannot
                    be overridden.
                  </p>
                </div>
              )}

              {tab === "artifacts" && (
                <ArtifactsPanel
                  storyId={storyId}
                  jiraKey={story.jira_key}
                  githubRepo={story.github_repo}
                  githubBranch={story.github_branch}
                  actor={actor}
                />
              )}

              {tab === "timeline" && (
                <ol className="relative ml-2 flex flex-col gap-0 border-l border-line pl-4">
                  {(timelineQuery.data ?? []).map((event) => (
                    <li key={event.id} className="relative pb-3">
                      <span className="absolute -left-[22.5px] top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full border border-line bg-panel text-[8px] text-ink-dim">
                        {EVENT_ICONS[event.event_type] ?? "·"}
                      </span>
                      <div className="flex items-baseline gap-2">
                        <span className="text-[11px] font-medium text-ink">
                          {event.event_type.replaceAll("_", " ")}
                        </span>
                        <span className="text-[10px] text-ink-faint">
                          {event.actor} · {fmtTime(event.created_at)}
                        </span>
                      </div>
                      {typeof event.payload.reason === "string" && (
                        <p className="text-[10px] italic text-ink-dim">
                          “{event.payload.reason}”
                        </p>
                      )}
                      {typeof event.payload.rationale === "string" && (
                        <p className="text-[10px] italic text-ink-dim">
                          “{event.payload.rationale}”
                        </p>
                      )}
                      {typeof event.payload.guidance === "string" && (
                        <p className="text-[10px] italic text-review">
                          guidance: “{event.payload.guidance}”
                        </p>
                      )}
                    </li>
                  ))}
                  {timelineQuery.data?.length === 0 && (
                    <p className="text-xs text-ink-faint">No events yet.</p>
                  )}
                </ol>
              )}

              {tab === "details" && (
                <div className="flex flex-col gap-4 text-xs">
                  <div>
                    <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                      Description
                    </h4>
                    <p className="whitespace-pre-wrap font-serif italic leading-relaxed text-ink">
                      {story.description ?? "—"}
                    </p>
                  </div>
                  <div>
                    <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                      Acceptance criteria
                    </h4>
                    {story.acceptance_criteria.length ? (
                      <ol className="flex flex-col gap-1.5 text-ink">
                        {story.acceptance_criteria.map((ac, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="font-mono text-[10px] text-accent">
                              AC-{i + 1}
                            </span>
                            <span>{ac}</span>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <p className="text-ink-faint">None captured.</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-ink-dim">
                    <span>Sprint</span>
                    <span className="text-ink">{story.sprint ?? "—"}</span>
                    <span>Jira status</span>
                    <span className="text-ink">{story.jira_status ?? "—"}</span>
                    <span>Assignee</span>
                    <span className="text-ink">{story.assignee ?? "—"}</span>
                    <span>Priority</span>
                    <span className="text-ink">{story.priority ?? "—"}</span>
                    <span>Labels</span>
                    <span className="text-ink">{story.labels.join(", ") || "—"}</span>
                    <span>Last synced</span>
                    <span className="text-ink">{fmtTime(story.last_synced_at)}</span>
                    <span>Jira updated</span>
                    <span className="text-ink">{fmtTime(story.jira_updated_at)}</span>
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
