import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { AgentDef, Gate, Run, StoryDetail } from "../types";
import { Badge, Button, Field, inputCls, Modal, useToast } from "../ui";

const CHALLENGE_KIND_LABEL: Record<string, string> = {
  CONTRADICTION: "contradiction",
  BLOCKING_QUESTION: "blocking question",
  SEVERE_FINDING: "severe finding",
  UNCOVERED_EVIDENCE: "uncovered evidence",
  SELF_REPORTED_CAVEAT: "self-reported caveat",
};

const ROLES = [
  "Product Owner",
  "Tech Lead",
  "QE Lead",
  "Business Stakeholder",
  "Compliance Officer",
];

const GATE_TITLES: Record<string, string> = {
  REFINEMENT: "Gate 1 — Refinement Sign-Off",
  DEVELOPMENT: "Gate 2 — Development Sign-Off",
  TESTING: "Gate 3 — Testing Sign-Off",
  RELEASE: "Gate 4 — Release Sign-Off",
};

export function GateModal({
  gate,
  story,
  agents,
  actor,
  onClose,
}: {
  gate: Gate;
  story: StoryDetail;
  agents: Map<string, AgentDef>;
  actor: string;
  onClose: () => void;
}) {
  const [name, setName] = useState(actor);
  const [role, setRole] = useState(ROLES[0]);
  const [rationale, setRationale] = useState("");
  const toast = useToast();
  const queryClient = useQueryClient();

  // Evidence checklist: latest run per agent in this phase.
  const latestByAgent = new Map<string, Run>();
  for (const run of story.runs.filter((r) => r.phase === gate.phase)) {
    const current = latestByAgent.get(run.agent_key);
    if (!current || run.attempt > current.attempt) latestByAgent.set(run.agent_key, run);
  }
  const evidence = Array.from(latestByAgent.values()).sort(
    (a, b) => a.sequence - b.sequence,
  );
  const blocked = evidence.some((r) => r.output_json?.release_blocking === true);

  const decide = useMutation({
    mutationFn: (kind: "signoff" | "reject") =>
      kind === "signoff"
        ? api.signoffGate(gate.id, name, role, rationale)
        : api.rejectGate(gate.id, name, role, rationale),
    onSuccess: (g) => {
      toast(
        g.status === "SIGNED_OFF" ? "ok" : "info",
        g.status === "SIGNED_OFF"
          ? `${GATE_TITLES[gate.phase]} recorded — ${name} (${role}). Jira posts queued per gate settings.`
          : "Gate rejected — decision recorded.",
      );
      queryClient.invalidateQueries();
      onClose();
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const ready = name.trim() && role && rationale.trim();

  return (
    <Modal title={GATE_TITLES[gate.phase]} onClose={onClose} wide>
      <div className="mb-4 rounded-lg border border-accent/30 bg-accent/5 px-3 py-2 text-[11px] leading-relaxed text-ink-dim">
        <span className="font-semibold text-accent">Formal sign-off. </span>
        Your name, role and rationale are recorded immutably in the
        hash-chained audit trail and posted to{" "}
        <span className="font-mono">{story.jira_key}</span> per the gate
        settings. Signing off advances the story to the next phase.
      </div>

      {/* Evidence checklist */}
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
        Evidence checklist
      </h3>
      <ul className="mb-4 flex flex-col gap-1.5">
        {evidence.map((run) => {
          const agent = agents.get(run.agent_key);
          const accepted = run.status === "ACCEPTED";
          const runBlocked = run.output_json?.release_blocking === true;
          return (
            <li
              key={run.id}
              className="flex items-center gap-2 rounded border border-line bg-bg/50 px-2.5 py-1.5 text-xs"
            >
              <span className={accepted && !runBlocked ? "text-ok" : "text-bad"}>
                {accepted && !runBlocked ? "✓" : "✗"}
              </span>
              <span className="text-ink">{agent?.name ?? run.agent_key}</span>
              <span className="ml-auto flex items-center gap-2 font-mono text-[10px] text-ink-faint">
                {run.attempt > 1 && <span>attempt {run.attempt}</span>}
                {run.approved_by && <span>run: {run.approved_by}</span>}
                {run.decided_by && <span>accepted: {run.decided_by}</span>}
                {run.output_hash && <span>#{run.output_hash.slice(0, 8)}</span>}
              </span>
              {runBlocked && (
                <Badge className="border-bad/60 bg-bad/15 text-bad">blocking</Badge>
              )}
            </li>
          );
        })}
      </ul>

      {blocked && (
        <div className="mb-4 rounded border border-bad/50 bg-bad/10 px-3 py-2 text-xs text-bad">
          ⛔ Release-blocking findings present (FCA scenario / financial data
          integrity). This gate cannot be signed off — there is no override.
          Resolve and re-run the agent.
        </div>
      )}

      <ChallengePanel storyId={story.id} phase={gate.phase} />

      {/* Sign-off record */}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Approver name">
          <input value={name} onChange={(e) => setName(e.target.value)} className={inputCls} />
        </Field>
        <Field label="Role">
          <select value={role} onChange={(e) => setRole(e.target.value)} className={inputCls}>
            {ROLES.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </Field>
      </div>
      <div className="mt-3">
        <Field label="Decision rationale (required — recorded verbatim)">
          <textarea
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={3}
            className={inputCls}
            placeholder="e.g. INVEST compliant, FCA impact classified HIGH, Gherkin scenarios approved by PO and QE."
          />
        </Field>
      </div>

      <div className="mt-5 flex items-center justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="danger"
          disabled={!ready}
          busy={decide.isPending}
          onClick={() => decide.mutate("reject")}
        >
          Reject gate
        </Button>
        <Button
          variant="ok"
          disabled={!ready || blocked}
          busy={decide.isPending}
          onClick={() => decide.mutate("signoff")}
        >
          ✒ Sign off {GATE_TITLES[gate.phase].split(" — ")[0]}
        </Button>
      </div>
    </Modal>
  );
}

/** Adversarial Challenger: the red-team pass pinned to the sign-off — the
 *  strongest case AGAINST the results you are about to attest to. Advisory
 *  only; it cannot block the gate. */
function ChallengePanel({ storyId, phase }: { storyId: string; phase: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["challenges", storyId, phase],
    queryFn: () => api.challenges(storyId, phase),
  });
  if (isLoading || !data) return null;
  return (
    <div className="mb-4">
      <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">
        Challenger — the case against ({data.count})
      </h3>
      {data.count === 0 ? (
        <div className="rounded border border-line bg-bg/50 px-3 py-2 text-[11px] text-ink-faint">
          No challenges raised — the red-team pass found nothing to contest.
        </div>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {data.challenges.map((c, i) => (
            <li
              key={i}
              className="rounded border border-warn/40 bg-warn/5 px-2.5 py-1.5 text-[11px]"
            >
              <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                <Badge className="border-warn/50 bg-warn/10 text-warn">
                  {CHALLENGE_KIND_LABEL[c.kind] ?? c.kind.toLowerCase()}
                </Badge>
                <span className="font-mono text-[10px] text-ink-faint">
                  {c.agent_name}
                </span>
              </div>
              <div className="text-ink">{c.challenge}</div>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-1.5 text-[10px] italic text-ink-faint">{data.note}</div>
    </div>
  );
}
