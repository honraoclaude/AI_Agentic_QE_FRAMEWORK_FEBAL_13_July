import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "./api";
import { AuditView } from "./components/AuditView";
import { InsightsView } from "./components/InsightsView";
import { PipelineBoard } from "./components/PipelineBoard";
import { PushQueueView } from "./components/PushQueueView";
import { SettingsPage } from "./components/SettingsPage";
import { WorkQueue } from "./components/WorkQueue";
import { ROLES, type Role } from "./types";
import { Button, inputCls, useToast } from "./ui";
import { useLiveUpdates } from "./ws";

type Tab = "work" | "board" | "insights" | "push" | "audit" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "work", label: "My Work" },
  { id: "board", label: "Pipeline" },
  { id: "insights", label: "Agent Insights" },
  { id: "push", label: "Jira Push Queue" },
  { id: "audit", label: "Audit Trail" },
  { id: "settings", label: "Settings" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("work");
  const [actor, setActor] = useState(() => localStorage.getItem("pact_actor") ?? "");
  const [role, setRole] = useState<Role>(
    () => (localStorage.getItem("pact_role") as Role) || "QE Lead",
  );
  const connected = useLiveUpdates();
  const toast = useToast();
  const queryClient = useQueryClient();

  const workQuery = useQuery({
    queryKey: ["work", role],
    queryFn: () => api.work(role),
  });
  const workCount = workQuery.data?.items.length ?? 0;

  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => (await fetch("/health")).json() as Promise<{ demo_mode: boolean }>,
    refetchInterval: 60000,
  });

  const syncMutation = useMutation({
    mutationFn: () => api.sync(actor || "unnamed-user"),
    onSuccess: (r) => {
      toast(
        "ok",
        `Sync complete: ${r.total} stories — ${r.created} new, ${r.updated} updated` +
          (r.out_of_scope ? `, ${r.out_of_scope} out of scope` : "") +
          (r.flagged_conflicts.length
            ? `. Changed since agent run: ${r.flagged_conflicts.join(", ")}`
            : ""),
      );
      queryClient.invalidateQueries();
    },
    onError: (e: Error) => toast("error", `Sync failed: ${e.message}`),
  });

  const setActorPersist = (v: string) => {
    setActor(v);
    localStorage.setItem("pact_actor", v);
  };
  const setRolePersist = (v: Role) => {
    setRole(v);
    localStorage.setItem("pact_role", v);
  };

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center gap-4 border-b border-line bg-panel/80 px-5 py-3 backdrop-blur">
        <div className="flex flex-col gap-0.5">
          <span className="font-mono text-lg font-bold tracking-tight text-accent">
            AI Agentic <span className="text-ink">QE Platform</span>
          </span>
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-ink-faint">
            AI That Tests. Humans Who Trust.
          </span>
        </div>

        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                tab === t.id
                  ? "bg-accent/15 text-accent"
                  : "text-ink-dim hover:bg-panel-2 hover:text-ink"
              }`}
            >
              {t.label}
              {t.id === "work" && workCount > 0 && (
                <span className="rounded-full bg-warn/20 px-1.5 text-[10px] font-bold text-warn">
                  {workCount}
                </span>
              )}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          {health.data?.demo_mode && (
            <span className="rounded border border-warn/40 bg-warn/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
              Demo mode
            </span>
          )}
          <span
            title={connected ? "Live updates connected" : "Reconnecting — polling fallback active"}
            className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-faint"
          >
            <span
              className={`h-2 w-2 rounded-full ${connected ? "bg-ok" : "bg-warn animate-pulse-dot"}`}
            />
            {connected ? "Live" : "Polling"}
          </span>
          <select
            value={role}
            onChange={(e) => setRolePersist(e.target.value as Role)}
            title="Your role — drives your work queue"
            className={`${inputCls} w-44`}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <input
            value={actor}
            onChange={(e) => setActorPersist(e.target.value)}
            placeholder="Your name (required for actions)"
            className={`${inputCls} w-52`}
          />
          <Button
            variant="primary"
            busy={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            ⟳ Sync from Jira
          </Button>
        </div>
      </header>

      <main className="min-h-0 flex-1 overflow-auto">
        {tab === "work" && (
          <WorkQueue role={role} actor={actor} onGoToPush={() => setTab("push")} />
        )}
        {tab === "board" && <PipelineBoard actor={actor} />}
        {tab === "insights" && <InsightsView />}
        {tab === "push" && <PushQueueView actor={actor} />}
        {tab === "audit" && <AuditView />}
        {tab === "settings" && <SettingsPage actor={actor} />}
      </main>
    </div>
  );
}
