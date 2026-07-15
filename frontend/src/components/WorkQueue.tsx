import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { AgentDef, Role, WorkItem, WorkKind } from "../types";
import { Badge, fmtTime } from "../ui";
import { StoryDrawer } from "./StoryDrawer";

const KIND_META: Record<
  WorkKind,
  { label: string; cls: string; group: string }
> = {
  GATE_SIGNOFF: {
    label: "Gate sign-off",
    cls: "border-warn/50 bg-warn/10 text-warn",
    group: "Gate approvals",
  },
  RUN_DECISION: {
    label: "Review output",
    cls: "border-review/50 bg-review/10 text-review",
    group: "Agent runs",
  },
  RUN_APPROVAL: {
    label: "Approve & run",
    cls: "border-accent/50 bg-accent/10 text-accent",
    group: "Agent runs",
  },
  PUSH_RETRY: {
    label: "Retry push",
    cls: "border-bad/50 bg-bad/10 text-bad",
    group: "Jira pushes",
  },
  PUSH_APPROVAL: {
    label: "Approve push",
    cls: "border-line text-ink-dim",
    group: "Jira pushes",
  },
};

const GROUP_ORDER = ["Gate approvals", "Agent runs", "Jira pushes"];

function WorkRow({
  item,
  onOpen,
}: {
  item: WorkItem;
  onOpen: (item: WorkItem) => void;
}) {
  const meta = KIND_META[item.kind];
  return (
    <button
      onClick={() => onOpen(item)}
      className="flex w-full items-center gap-3 rounded-lg border border-line bg-panel px-4 py-3 text-left transition-colors hover:border-accent/50"
    >
      <Badge className={meta.cls}>{meta.label}</Badge>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-accent">{item.jira_key}</span>
          {item.phase && (
            <span className="text-[10px] uppercase tracking-wider text-ink-faint">
              {item.phase}
            </span>
          )}
          <span className="truncate text-xs font-medium text-ink">{item.title}</span>
        </div>
        <p className="truncate text-[11px] text-ink-dim">{item.detail}</p>
        <p className="truncate text-[10px] text-ink-faint">{item.reason}</p>
      </div>
      <div className="shrink-0 text-right">
        {item.since && (
          <div className="font-mono text-[10px] text-ink-faint">
            waiting since {fmtTime(item.since)}
          </div>
        )}
        <span className="text-[11px] font-medium text-accent">Open →</span>
      </div>
    </button>
  );
}

export function WorkQueue({
  role,
  actor,
  onGoToPush,
}: {
  role: Role;
  actor: string;
  onGoToPush: () => void;
}) {
  const [drawer, setDrawer] = useState<{
    storyId: string;
    tab: "runs" | "gates";
    gateId?: string;
  } | null>(null);

  const workQuery = useQuery({
    queryKey: ["work", role],
    queryFn: () => api.work(role),
  });
  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: api.agents,
    staleTime: Infinity,
  });

  const agents = useMemo(
    () => new Map((agentsQuery.data ?? []).map((a: AgentDef) => [a.key, a])),
    [agentsQuery.data],
  );

  const items = workQuery.data?.items ?? [];

  const grouped = useMemo(() => {
    const map = new Map<string, WorkItem[]>();
    for (const item of items) {
      const group = KIND_META[item.kind].group;
      map.set(group, [...(map.get(group) ?? []), item]);
    }
    return map;
  }, [items]);

  const openItem = (item: WorkItem) => {
    if (item.action === "APPROVE_PUSH" || item.action === "RETRY_PUSH") {
      onGoToPush();
      return;
    }
    if (item.action === "SIGN_GATE") {
      setDrawer({ storyId: item.story_id, tab: "gates", gateId: item.entity_id });
    } else {
      // Run approval / decision -> open the runs tab.
      setDrawer({ storyId: item.story_id, tab: "runs" });
    }
  };

  return (
    <div className="mx-auto max-w-4xl p-5">
      <div className="mb-4 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">
          Work queue for{" "}
          <span className="text-accent">{role}</span>
        </h2>
        <p className="mt-0.5 text-[11px] leading-relaxed text-ink-dim">
          Everything currently waiting on your role — gate sign-offs assigned to
          you{role === "QE Lead" ? ", plus agent runs and Jira pushes you operate" : ""}.
          Items update live as the pipeline moves.
        </p>
      </div>

      {workQuery.isLoading && (
        <p className="py-10 text-center text-sm text-ink-faint">Loading your work…</p>
      )}

      {!workQuery.isLoading && items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16">
          <span className="text-3xl">✓</span>
          <p className="text-sm text-ink-dim">Nothing is waiting on {role} right now.</p>
          <p className="text-[11px] text-ink-faint">
            When a gate you approve becomes ready — or an agent needs running (QE
            Lead) — it will appear here.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-5">
        {GROUP_ORDER.filter((g) => grouped.has(g)).map((group) => {
          const groupItems = grouped.get(group)!;
          return (
            <section key={group}>
              <h3 className="mb-2 flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.15em] text-ink-faint">
                {group}
                <span className="rounded-full bg-panel-2 px-1.5 py-0.5 font-mono text-ink-dim">
                  {groupItems.length}
                </span>
              </h3>
              <div className="flex flex-col gap-2">
                {groupItems.map((item) => (
                  <WorkRow
                    key={`${item.kind}-${item.entity_id}`}
                    item={item}
                    onOpen={openItem}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {drawer && (
        <StoryDrawer
          storyId={drawer.storyId}
          actor={actor}
          agents={agents}
          initialTab={drawer.tab}
          autoOpenGateId={drawer.gateId}
          onClose={() => setDrawer(null)}
        />
      )}
    </div>
  );
}
