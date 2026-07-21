import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "./api";
import { AuditView } from "./components/AuditView";
import { InsightsView } from "./components/InsightsView";
import { ReportsView } from "./components/ReportsView";
import { RiskRegisterView } from "./components/RiskRegisterView";
import { PipelineBoard } from "./components/PipelineBoard";
import { PushQueueView } from "./components/PushQueueView";
import { SettingsPage } from "./components/SettingsPage";
import { WorkQueue } from "./components/WorkQueue";
import { ROLES, type Role } from "./types";
import { useToast } from "./ui";
import { useLiveUpdates } from "./ws";

type Theme = "light" | "dark";

function resolveInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem("pact_theme");
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    /* localStorage unavailable */
  }
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function SunIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
    </svg>
  );
}
function MoonIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z" />
    </svg>
  );
}

type Tab = "work" | "board" | "insights" | "risks" | "reports" | "push" | "audit" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "work", label: "My Work" },
  { id: "board", label: "Pipeline" },
  { id: "insights", label: "Agent Insights" },
  { id: "risks", label: "Risk Register" },
  { id: "reports", label: "Reports" },
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
  const [theme, setThemeState] = useState<Theme>(resolveInitialTheme);
  const connected = useLiveUpdates();
  const toast = useToast();
  const queryClient = useQueryClient();

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = (t: Theme) => {
    setThemeState(t);
    try {
      localStorage.setItem("pact_theme", t);
    } catch {
      /* localStorage unavailable */
    }
  };

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
      <div className="masthead">
        <div className="masthead-inner">
          <div>
            <div className="eyebrow">
              <span className="pulse" />
              Compliance Operations &middot; Live Session
            </div>
            <h1 className="brand">
              AI Agentic <em>QE</em>
            </h1>
            <div className="tagline" style={{ color: "#fff" }}>
              AI That Tests. Humans Who Trust.
            </div>
          </div>
          <div className="masthead-meta">
            <div className="meta-block">
              <div className="meta-label">FCA Impact Key</div>
              <div className="tier-key">
                <span className="tier-chip low">Low</span>
                <span className="tier-chip med">Med</span>
                <span className="tier-chip high">High</span>
              </div>
            </div>
            <div className="meta-block">
              <div className="meta-label">Session</div>
              <div className="meta-value">
                {new Date().toLocaleDateString(undefined, {
                  day: "2-digit",
                  month: "short",
                  year: "numeric",
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      <nav className="navstrip">
        <div className="navlinks">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={tab === t.id ? "active" : ""}
            >
              {t.label}
              {t.id === "work" && workCount > 0 && (
                <span className="nav-badge">{workCount}</span>
              )}
            </button>
          ))}
        </div>

        <div className="navctl">
          {health.data?.demo_mode && <span className="demo-pill">Demo Mode</span>}
          <span
            className="live-pill"
            title={connected ? "Live updates connected" : "Reconnecting — polling fallback active"}
          >
            {connected ? (
              <span className="pulse" />
            ) : (
              <span
                className="h-2 w-2 rounded-full bg-warn animate-pulse-dot"
                style={{ display: "inline-block" }}
              />
            )}
            {connected ? "Live" : "Polling"}
          </span>
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button
              type="button"
              onClick={() => setTheme("light")}
              aria-pressed={theme === "light"}
              title="Light theme"
              className={theme === "light" ? "theme-btn active" : "theme-btn"}
            >
              <SunIcon /> Light
            </button>
            <button
              type="button"
              onClick={() => setTheme("dark")}
              aria-pressed={theme === "dark"}
              title="Dark theme"
              className={theme === "dark" ? "theme-btn active" : "theme-btn"}
            >
              <MoonIcon /> Dark
            </button>
          </div>
          <select
            value={role}
            onChange={(e) => setRolePersist(e.target.value as Role)}
            title="Your role — drives your work queue"
            className="role-select"
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
            placeholder="Your name"
            title="Your name — required for actions"
            className="role-select"
            style={{ width: 150 }}
          />
          <button
            type="button"
            className="sync-btn"
            disabled={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            &#8635; Sync from Jira
          </button>
        </div>
      </nav>

      <main className="min-h-0 flex-1 overflow-auto">
        {tab === "work" && (
          <WorkQueue role={role} actor={actor} onGoToPush={() => setTab("push")} />
        )}
        {tab === "board" && <PipelineBoard actor={actor} />}
        {tab === "insights" && <InsightsView actor={actor} />}
        {tab === "risks" && <RiskRegisterView actor={actor} />}
        {tab === "reports" && <ReportsView actor={actor} />}
        {tab === "push" && <PushQueueView actor={actor} />}
        {tab === "audit" && <AuditView />}
        {tab === "settings" && <SettingsPage actor={actor} />}
      </main>
    </div>
  );
}
