import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api";
import type { Phase, SettingsView } from "../types";
import { PHASES } from "../types";
import { Badge, Button, Field, inputCls, useToast } from "../ui";

const GATE_LABELS: Record<Phase, string> = {
  REFINEMENT: "Gate 1 · Refinement",
  DEVELOPMENT: "Gate 2 · Development",
  TESTING: "Gate 3 · Testing",
  RELEASE: "Gate 4 · Release",
};

export function SettingsPage({ actor }: { actor: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [draft, setDraft] = useState<SettingsView["settings"] | null>(null);
  const [testing, setTesting] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (settingsQuery.data) setDraft(structuredClone(settingsQuery.data.settings));
  }, [settingsQuery.data]);

  const save = useMutation({
    mutationFn: (patch: Record<string, unknown>) =>
      api.updateSettings(actor || "unnamed-user", patch),
    onSuccess: () => {
      toast("ok", "Settings saved");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const testConn = useMutation({
    mutationFn: api.testConnection,
    onSuccess: (r) => {
      setTesting(r);
      toast(r.ok ? "ok" : "error", r.ok ? "Connection OK" : `Failed: ${r.error}`);
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const env = settingsQuery.data?.env;
  if (!draft || !env) {
    return <div className="p-6 text-sm text-ink-faint">Loading settings…</div>;
  }

  const updateGate = (phase: Phase, patch: Record<string, unknown>) =>
    setDraft((d) =>
      d ? { ...d, gates: { ...d.gates, [phase]: { ...d.gates[phase], ...patch } } } : d,
    );

  return (
    <div className="mx-auto max-w-3xl p-5">
      {/* Environment (read-only, secret-safe) */}
      <section className="mb-6 rounded-lg border border-line bg-panel p-4">
        <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-ink-dim">
          Environment (from .env — read only)
        </h2>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <span className="text-ink-faint">Mode</span>
          <span>
            {env.demo_mode ? (
              <Badge className="border-warn/40 bg-warn/10 text-warn">Demo (mock Jira)</Badge>
            ) : (
              <Badge className="border-ok/40 bg-ok/10 text-ok">Live Jira</Badge>
            )}
          </span>
          <span className="text-ink-faint">Jira base URL</span>
          <span className="text-ink">{env.jira_base_url || "—"}</span>
          <span className="text-ink-faint">Jira token</span>
          <span className={env.jira_api_token_set ? "text-ok" : "text-ink-faint"}>
            {env.jira_api_token_set ? "set ✓" : "not set"}
          </span>
          <span className="text-ink-faint">Anthropic key</span>
          <span className={env.anthropic_api_key_set ? "text-ok" : "text-ink-faint"}>
            {env.anthropic_api_key_set ? "set ✓ (real agents)" : "not set (stub agents)"}
          </span>
          <span className="text-ink-faint">Models</span>
          <span className="font-mono text-ink">
            {env.reasoning_model} / {env.classification_model}
          </span>
        </div>
        <div className="mt-3">
          <Button variant="ghost" busy={testConn.isPending} onClick={() => testConn.mutate()}>
            Test connection
          </Button>
          {testing && (
            <pre className="mt-2 overflow-auto rounded border border-line bg-bg p-2 font-mono text-[10px] text-ink-dim">
              {JSON.stringify(testing, null, 2)}
            </pre>
          )}
        </div>
      </section>

      {/* Jira project + sync */}
      <section className="mb-6 rounded-lg border border-line bg-panel p-4">
        <h2 className="mb-3 text-xs font-bold uppercase tracking-widest text-ink-dim">
          Jira project &amp; sync
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Project key">
            <input
              value={draft.jira.project_key}
              onChange={(e) =>
                setDraft({ ...draft, jira: { ...draft.jira, project_key: e.target.value } })
              }
              className={inputCls}
            />
          </Field>
          <Field label="Board ID">
            <input
              type="number"
              value={draft.jira.board_id}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  jira: { ...draft.jira, board_id: Number(e.target.value) },
                })
              }
              className={inputCls}
            />
          </Field>
        </div>
        <div className="mt-3">
          <Field label="JQL override (blank = configured sprint)">
            <input
              value={draft.jira.jql_override}
              onChange={(e) =>
                setDraft({ ...draft, jira: { ...draft.jira, jql_override: e.target.value } })
              }
              placeholder='project = "WLTH" AND sprint in openSprints()'
              className={inputCls}
            />
          </Field>
        </div>
        <div className="mt-3 flex items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-ink">
            <input
              type="checkbox"
              checked={draft.sync.enabled}
              onChange={(e) =>
                setDraft({ ...draft, sync: { ...draft.sync, enabled: e.target.checked } })
              }
            />
            Scheduled background sync
          </label>
          <label className="flex items-center gap-2 text-xs text-ink-dim">
            every
            <input
              type="number"
              min={1}
              value={draft.sync.interval_minutes}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  sync: { ...draft.sync, interval_minutes: Number(e.target.value) },
                })
              }
              className={`${inputCls} w-20`}
            />
            minutes
          </label>
        </div>
      </section>

      {/* Per-gate push behaviour */}
      <section className="mb-6 rounded-lg border border-line bg-panel p-4">
        <h2 className="mb-1 text-xs font-bold uppercase tracking-widest text-ink-dim">
          Per-gate Jira automation
        </h2>
        <p className="mb-3 text-[10px] text-ink-faint">
          On sign-off (the human approval), auto-post a structured comment, apply a
          label, and optionally transition the issue. Transitions are resolved by
          name against the issue's available transitions at send time.
        </p>
        <div className="flex flex-col gap-3">
          {PHASES.map((phase) => {
            const g = draft.gates[phase];
            if (!g) return null;
            return (
              <div key={phase} className="rounded border border-line bg-bg/40 p-3">
                <div className="mb-2 text-[11px] font-semibold text-ink">
                  {GATE_LABELS[phase]}
                </div>
                <div className="flex flex-wrap items-center gap-4">
                  <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                    <input
                      type="checkbox"
                      checked={g.auto_post_comment}
                      onChange={(e) => updateGate(phase, { auto_post_comment: e.target.checked })}
                    />
                    Auto comment
                  </label>
                  <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                    <input
                      type="checkbox"
                      checked={g.apply_label}
                      onChange={(e) => updateGate(phase, { apply_label: e.target.checked })}
                    />
                    Label
                  </label>
                  <input
                    value={g.label}
                    onChange={(e) => updateGate(phase, { label: e.target.value })}
                    className={`${inputCls} w-40`}
                  />
                  <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                    Transition to
                    <input
                      value={g.transition_name ?? ""}
                      onChange={(e) =>
                        updateGate(phase, { transition_name: e.target.value || null })
                      }
                      placeholder="(none)"
                      className={`${inputCls} w-40`}
                    />
                  </label>
                  {phase === "RELEASE" && (
                    <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                      <input
                        type="checkbox"
                        checked={g.attach_evidence ?? false}
                        onChange={(e) => updateGate(phase, { attach_evidence: e.target.checked })}
                      />
                      Attach release audit pack
                    </label>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="flex justify-end gap-2">
        <Button
          variant="ghost"
          onClick={() =>
            settingsQuery.data && setDraft(structuredClone(settingsQuery.data.settings))
          }
        >
          Revert
        </Button>
        <Button
          variant="primary"
          busy={save.isPending}
          onClick={() =>
            save.mutate({
              jira: draft.jira,
              sync: draft.sync,
              gates: draft.gates,
            })
          }
        >
          Save settings
        </Button>
      </div>
    </div>
  );
}
