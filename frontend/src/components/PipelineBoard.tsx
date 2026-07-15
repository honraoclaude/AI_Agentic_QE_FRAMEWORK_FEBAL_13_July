import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { AgentDef, Phase, StoryBoard } from "../types";
import { PHASES } from "../types";
import { Badge, Button, GATE_STATUS_META, RUN_STATUS_META, useToast } from "../ui";
import { StoryDrawer } from "./StoryDrawer";

const PHASE_LABELS: Record<Phase, string> = {
  REFINEMENT: "1 · Refinement",
  DEVELOPMENT: "2 · Development",
  TESTING: "3 · Testing",
  RELEASE: "4 · Release",
};

const FCA_COLORS: Record<string, string> = {
  HIGH: "border-bad/50 text-bad bg-bad/10",
  MEDIUM: "border-warn/50 text-warn bg-warn/10",
  LOW: "border-ok/40 text-ok bg-ok/10",
};

const CLOUD_COLORS: Record<string, string> = {
  FSC: "border-sky-400/40 text-sky-300",
  SALES: "border-indigo-400/40 text-indigo-300",
  MARKETING: "border-pink-400/40 text-pink-300",
};

function StoryCard({
  story,
  agents,
  onOpen,
}: {
  story: StoryBoard;
  agents: Map<string, AgentDef>;
  onOpen: () => void;
}) {
  const phaseRuns = story.runs
    .filter((r) => r.phase === story.current_phase)
    .sort((a, b) => a.sequence - b.sequence);
  const gate = story.gates.find((g) => g.phase === story.current_phase);
  const gateMeta = gate ? GATE_STATUS_META[gate.status] : null;

  return (
    <button
      onClick={onOpen}
      className={`w-full rounded-lg border bg-panel p-3 text-left transition-all hover:border-accent/50 hover:shadow-[0_0_20px_rgba(56,189,248,0.08)] ${
        story.scope_status === "OUT_OF_SCOPE"
          ? "border-line opacity-45"
          : "border-line"
      }`}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className="font-mono text-xs font-semibold text-accent">
          {story.jira_key}
        </span>
        {story.cloud && (
          <Badge className={CLOUD_COLORS[story.cloud] ?? "border-line text-ink-dim"}>
            {story.cloud}
          </Badge>
        )}
        {story.fca_impact && (
          <Badge className={FCA_COLORS[story.fca_impact]}>
            FCA {story.fca_impact}
            {!story.fca_impact_confirmed && " ?"}
          </Badge>
        )}
        {story.story_points != null && (
          <span className="ml-auto font-mono text-[10px] text-ink-faint">
            {story.story_points}pt
          </span>
        )}
      </div>

      <p className="mb-2 line-clamp-2 text-xs leading-snug text-ink">
        {story.summary}
      </p>

      {story.changed_since_agent_run && (
        <div className="mb-2 rounded border border-warn/40 bg-warn/10 px-2 py-1 text-[10px] font-medium text-warn">
          ⚠ Jira changed since last agent run
        </div>
      )}
      {story.scope_status === "OUT_OF_SCOPE" && (
        <div className="mb-2 rounded border border-line px-2 py-1 text-[10px] font-medium text-ink-faint">
          Out of scope — removed from sprint (history preserved)
        </div>
      )}
      {story.released && (
        <div className="mb-2 rounded border border-ok/40 bg-ok/10 px-2 py-1 text-[10px] font-medium text-ok">
          ✓ Released — all four gates signed off
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {phaseRuns.map((run) => {
            const meta = RUN_STATUS_META[run.status];
            const agent = agents.get(run.agent_key);
            return (
              <span
                key={run.id}
                title={`${agent?.name ?? run.agent_key} — ${meta.label}${run.attempt > 1 ? ` (attempt ${run.attempt})` : ""}`}
                className={`h-2.5 w-2.5 rounded-full ${meta.dot}`}
              />
            );
          })}
        </div>
        {gateMeta && (
          <span
            className={`rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${gateMeta.cls}`}
          >
            Gate: {gateMeta.label}
          </span>
        )}
      </div>
    </button>
  );
}

export function PipelineBoard({ actor }: { actor: string }) {
  const [openStoryId, setOpenStoryId] = useState<string | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();

  const storiesQuery = useQuery({ queryKey: ["stories"], queryFn: api.stories });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: api.agents,
    staleTime: Infinity,
  });

  const seedMutation = useMutation({
    mutationFn: api.seedDemo,
    onSuccess: (r) => {
      toast("ok", `Demo sprint seeded: ${r.created} stories`);
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const agents = useMemo(
    () => new Map((agentsQuery.data ?? []).map((a) => [a.key, a])),
    [agentsQuery.data],
  );

  const stories = storiesQuery.data ?? [];

  if (storiesQuery.isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-ink-faint">
        Loading pipeline…
      </div>
    );
  }

  if (stories.length === 0) {
    return (
      <div className="flex h-72 flex-col items-center justify-center gap-4">
        <p className="text-sm text-ink-dim">
          No stories yet. Sync from Jira, or seed the demo sprint.
        </p>
        <Button
          variant="primary"
          busy={seedMutation.isPending}
          onClick={() => seedMutation.mutate()}
        >
          Seed demo sprint
        </Button>
      </div>
    );
  }

  return (
    <>
      <div className="grid min-w-[1000px] grid-cols-4 gap-4 p-5">
        {PHASES.map((phase) => {
          const inPhase = stories.filter(
            (s) => s.current_phase === phase && !(s.released && phase !== "RELEASE"),
          );
          return (
            <section key={phase} className="min-w-0">
              <header className="mb-3 flex items-center justify-between border-b border-line pb-2">
                <h2 className="text-xs font-bold uppercase tracking-[0.15em] text-ink-dim">
                  {PHASE_LABELS[phase]}
                </h2>
                <span className="font-mono text-[10px] text-ink-faint">
                  {inPhase.length}
                </span>
              </header>
              <div className="flex flex-col gap-2.5">
                {inPhase.map((story) => (
                  <StoryCard
                    key={story.id}
                    story={story}
                    agents={agents}
                    onOpen={() => setOpenStoryId(story.id)}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {openStoryId && (
        <StoryDrawer
          storyId={openStoryId}
          actor={actor}
          agents={agents}
          onClose={() => setOpenStoryId(null)}
        />
      )}
    </>
  );
}
