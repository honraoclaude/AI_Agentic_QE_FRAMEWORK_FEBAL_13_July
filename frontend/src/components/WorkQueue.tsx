import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "../api";
import type { AgentDef, Role, WorkItem, WorkKind } from "../types";
import { fmtTime } from "../ui";
import { StoryDrawer } from "./StoryDrawer";

const KIND_META: Record<WorkKind, { label: string; pill: string; group: string }> = {
  GATE_SIGNOFF: { label: "Gate sign-off", pill: "pill-warn", group: "Gate approvals" },
  RUN_DECISION: { label: "Review output", pill: "pill-accent", group: "Agent runs" },
  RUN_APPROVAL: { label: "Approve & run", pill: "pill-accent", group: "Agent runs" },
  PUSH_RETRY: { label: "Retry push", pill: "pill-crit", group: "Jira pushes" },
  PUSH_APPROVAL: { label: "Approve push", pill: "pill-slate", group: "Jira pushes" },
};

const GROUP_ORDER = ["Gate approvals", "Agent runs", "Jira pushes"];

function WorkRow({ item, onOpen }: { item: WorkItem; onOpen: (item: WorkItem) => void }) {
  const meta = KIND_META[item.kind];
  return (
    <button onClick={() => onOpen(item)} className="card" style={{ width: "100%", textAlign: "left" }}>
      <div className="flex items-center gap-3">
        <span className={`pill ${meta.pill}`}>{meta.label}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="card-id">{item.jira_key}</span>
            {item.phase && (
              <span className="font-mono text-[9.5px] uppercase tracking-wider text-ink-faint">
                {item.phase}
              </span>
            )}
            <span className="truncate text-[13px] font-medium text-ink">{item.title}</span>
          </div>
          <p className="truncate text-[11.5px] text-ink-dim">{item.detail}</p>
          <p className="truncate font-mono text-[10px] text-ink-faint">{item.reason}</p>
        </div>
        <div className="shrink-0 text-right">
          {item.since && (
            <div className="font-mono text-[10px] text-ink-faint">
              waiting since {fmtTime(item.since)}
            </div>
          )}
          <span className="font-mono text-[11px]" style={{ color: "var(--color-accent)" }}>Open →</span>
        </div>
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
    <div className="stage">
      <div className="board-head">
        <div className="board-title">My Work</div>
        <div className="board-sub">Everything currently waiting on {role}</div>
      </div>
      <div className="referee" style={{ borderLeftColor: "var(--color-accent)", background: "var(--accent-soft)", borderColor: "var(--accent-soft)" }}>
        <p style={{ margin: 0, color: "var(--color-ink)" }}>
          Gate sign-offs assigned to you
          {role === "QE Lead" ? ", plus agent runs and Jira pushes you operate" : ""}.
          Items update live as the pipeline moves.
        </p>
      </div>

      {workQuery.isLoading && (
        <p className="py-10 text-center text-sm text-ink-faint">Loading your work…</p>
      )}

      {!workQuery.isLoading && items.length === 0 && (
        <div className="flex flex-col items-center gap-2 py-16">
          <span className="text-3xl" style={{ color: "var(--color-ok)" }}>✓</span>
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
              <div className="section-label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {group}
                <span className="pill pill-slate">{groupItems.length}</span>
              </div>
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
