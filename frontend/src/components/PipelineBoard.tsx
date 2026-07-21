import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { Phase, RunStatus, StoryBoard } from "../types";
import { PHASES } from "../types";
import { GATE_STATUS_META, useToast } from "../ui";
import { StoryDrawer } from "./StoryDrawer";

const PHASE_LABELS: Record<Phase, string> = {
  REFINEMENT: "Refinement",
  DEVELOPMENT: "Development",
  TESTING: "Testing",
  RELEASE: "Release",
};
const PHASE_COL_CLASS: Record<Phase, string> = {
  REFINEMENT: "col-refinement",
  DEVELOPMENT: "col-dev",
  TESTING: "col-test",
  RELEASE: "col-release",
};

// Each run's status becomes one segment of the card's instrument meter.
const METER_CLASS: Record<RunStatus, string> = {
  ACCEPTED: "g",
  AWAITING_APPROVAL: "w",
  RUNNING: "p",
  COMPLETED: "w",
  REJECTED: "b",
  FAILED: "b",
  PROPOSED: "",
  RERUN_REQUESTED: "",
  SKIPPED: "",
};

const FCA_TIER: Record<string, string> = { HIGH: "high", MEDIUM: "med", LOW: "low" };

function StoryCard({
  story,
  onOpen,
  delay,
}: {
  story: StoryBoard;
  onOpen: () => void;
  delay: number;
}) {
  const phaseRuns = story.runs
    .filter((r) => r.phase === story.current_phase)
    .sort((a, b) => a.sequence - b.sequence);
  const gate = story.gates.find((g) => g.phase === story.current_phase);
  const gateMeta = gate ? GATE_STATUS_META[gate.status] : null;
  const gateReady = gate?.status === "READY_FOR_SIGNOFF" || gate?.status === "SIGNED_OFF";

  return (
    <button
      onClick={onOpen}
      className="card"
      style={{ animationDelay: `${delay}s`, opacity: story.scope_status === "OUT_OF_SCOPE" ? 0.5 : 1 }}
    >
      <div className="card-top">
        <span className="card-id">{story.jira_key}</span>
        {story.story_points != null && <span className="card-pt">{story.story_points}pt</span>}
      </div>
      <div className="chips">
        {story.cloud && <span className="chip">{story.cloud}</span>}
        {story.fca_impact && (
          <span className={`chip tier-${FCA_TIER[story.fca_impact] ?? "low"}`}>
            FCA {story.fca_impact}
            {!story.fca_impact_confirmed && " ?"}
          </span>
        )}
      </div>

      <p className="card-title">{story.summary}</p>

      {story.changed_since_agent_run && (
        <p className="mb-2 font-mono text-[10.5px]" style={{ color: "var(--color-warn)" }}>
          &#9888; Jira changed since last agent run
        </p>
      )}
      {story.scope_status === "OUT_OF_SCOPE" && (
        <p className="mb-2 font-mono text-[10.5px] text-ink-faint">
          Out of scope — history preserved
        </p>
      )}
      {story.released && (
        <p className="mb-2 font-mono text-[10.5px]" style={{ color: "var(--color-ok)" }}>
          &#10003; Released — all four gates signed off
        </p>
      )}

      {phaseRuns.length > 0 && (
        <div className="meter">
          {phaseRuns.map((run) => (
            <i key={run.id} className={METER_CLASS[run.status]} title={run.status} />
          ))}
        </div>
      )}

      {gateMeta && (
        <div className="card-foot">
          <span className={`seal ${gateReady ? "ready" : "locked"}`}>{gateMeta.label}</span>
        </div>
      )}
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
        <button
          type="button"
          className="sync-btn"
          disabled={seedMutation.isPending}
          onClick={() => seedMutation.mutate()}
        >
          Seed demo sprint
        </button>
      </div>
    );
  }

  const byPhase = PHASES.map((phase) => ({
    phase,
    stories: stories.filter(
      (s) => s.current_phase === phase && !(s.released && phase !== "RELEASE"),
    ),
  }));
  const summary = byPhase
    .map(({ phase, stories: s }) => `${s.length} ${PHASE_LABELS[phase].toLowerCase()}`)
    .join(" · ");

  return (
    <>
      <div className="stage">
        <div className="board-head">
          <div className="board-title">Pipeline</div>
          <div className="board-sub">{summary}</div>
        </div>

        <div className="board">
          {byPhase.map(({ phase, stories: inPhase }) => (
            <div key={phase}>
              <div className={`col-head ${PHASE_COL_CLASS[phase]}`}>
                <h3>{PHASE_LABELS[phase]}</h3>
                <span className="n">{inPhase.length}</span>
              </div>
              <div className="col-body">
                {inPhase.length === 0 ? (
                  <div className="empty-col">Nothing in flight</div>
                ) : (
                  inPhase.map((story, i) => (
                    <StoryCard
                      key={story.id}
                      story={story}
                      onOpen={() => setOpenStoryId(story.id)}
                      delay={i * 0.04}
                    />
                  ))
                )}
              </div>
            </div>
          ))}
        </div>
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
