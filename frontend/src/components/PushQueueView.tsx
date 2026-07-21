import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api";
import type { PushItem, PushStatus } from "../types";
import { Button, fmtTime, Modal, useToast } from "../ui";

const STATUS_PILL: Record<PushStatus, string> = {
  DRAFT: "pill-slate",
  APPROVED: "pill-accent",
  SENT: "pill-good",
  FAILED: "pill-crit",
  RETRYING: "pill-warn",
};

export function PushQueueView({ actor }: { actor: string }) {
  const [preview, setPreview] = useState<PushItem | null>(null);
  const toast = useToast();
  const queryClient = useQueryClient();
  const pushQuery = useQuery({ queryKey: ["push"], queryFn: () => api.pushQueue() });

  const action = useMutation({
    mutationFn: ({ id, kind }: { id: string; kind: "approve" | "retry" }) =>
      kind === "approve" ? api.approvePush(id, actor) : api.retryPush(id, actor),
    onSuccess: (item) => {
      queryClient.invalidateQueries({ queryKey: ["push"] });
      setPreview(null);
      if (item.status === "SENT") toast("ok", `Sent to ${item.payload.jira_key}`);
      else toast("error", `Failed: ${item.last_error}`);
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const items = pushQuery.data ?? [];

  return (
    <div className="stage">
      <div className="board-head">
        <div className="board-title">Jira Push Queue</div>
        <div className="board-sub">Outbound sync between QE gate decisions and Jira issue state</div>
      </div>
      <p className="queue-note">
        Every outbound Jira post lives here: drafts await your approval (with a
        preview of exactly what will be posted), failures keep their error and can
        be retried — approved posts are never lost.
      </p>
      <div className="flex flex-col gap-2">
        {items.map((item) => (
          <div key={item.id} className="panel-block" style={{ marginBottom: 0, padding: "12px 16px" }}>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className={`pill ${STATUS_PILL[item.status]}`}>{item.status}</span>
              <span className="chip">{item.push_type}</span>
              <span className="card-id">{String(item.payload.jira_key ?? "")}</span>
              <span className="truncate font-mono text-[11px] text-ink-dim">
                {String(item.payload.kind ?? "").replaceAll("_", " ")}
              </span>
              <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-faint">
                {item.attempts > 0 && `${item.attempts} attempt${item.attempts > 1 ? "s" : ""} · `}
                {fmtTime(item.updated_at)}
              </span>
              {item.payload.preview_text != null && (
                <button type="button" className="ghost-btn" onClick={() => setPreview(item)}>
                  Preview
                </button>
              )}
              {item.status === "DRAFT" && (
                <button
                  type="button"
                  className="sync-btn"
                  disabled={action.isPending}
                  onClick={() => action.mutate({ id: item.id, kind: "approve" })}
                >
                  Approve &amp; send
                </button>
              )}
              {item.status === "FAILED" && (
                <button
                  type="button"
                  className="ghost-btn"
                  style={{ borderColor: "var(--color-bad)", color: "var(--color-bad)" }}
                  disabled={action.isPending}
                  onClick={() => action.mutate({ id: item.id, kind: "retry" })}
                >
                  Retry
                </button>
              )}
            </div>
          </div>
        ))}
        {items.length === 0 && !pushQuery.isLoading && (
          <p className="py-10 text-center text-xs text-ink-faint">
            Queue is empty — accept an agent run or sign off a gate to create pushes.
          </p>
        )}
      </div>

      {preview && (
        <Modal title={`Preview — ${preview.push_type}`} onClose={() => setPreview(null)} wide>
          {preview.last_error && (
            <div className="mb-3 rounded border border-bad/40 bg-bad/10 px-2.5 py-1.5 text-[11px] text-bad">
              Last error: {preview.last_error}
            </div>
          )}
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded border border-line bg-bg p-3 font-mono text-[11px] leading-relaxed text-ink">
            {String(preview.payload.preview_text ?? "")}
          </pre>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPreview(null)}>
              Close
            </Button>
            {preview.status === "DRAFT" && (
              <button
                type="button"
                className="sync-btn"
                disabled={action.isPending}
                onClick={() => action.mutate({ id: preview.id, kind: "approve" })}
              >
                Approve &amp; send to Jira
              </button>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
