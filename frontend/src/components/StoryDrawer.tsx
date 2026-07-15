import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { AgentDef, Gate, Phase, Run } from "../types";
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
import { RunCard } from "./RunCard";

type DrawerTab = "runs" | "gates" | "artifacts" | "timeline" | "details";

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
              <h1 className="mt-2 text-sm font-medium leading-snug text-ink">
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
                          {phaseAgents.flatMap((agentDef) => {
                            const attempts = runsByAgent.get(agentDef.key) ?? [];
                            return attempts.map((run) => (
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
                            ));
                          })}
                        </div>
                      </section>
                    );
                  })}
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
                <ArtifactsPanel storyId={storyId} actor={actor} />
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
                    <p className="whitespace-pre-wrap leading-relaxed text-ink">
                      {story.description ?? "—"}
                    </p>
                  </div>
                  <div>
                    <h4 className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                      Acceptance criteria
                    </h4>
                    {story.acceptance_criteria.length ? (
                      <ul className="list-inside list-disc space-y-1 text-ink">
                        {story.acceptance_criteria.map((ac, i) => (
                          <li key={i}>{ac}</li>
                        ))}
                      </ul>
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
