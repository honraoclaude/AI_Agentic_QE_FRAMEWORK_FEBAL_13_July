import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api } from "../api";
import type { Artifact, ArtifactKind } from "../types";
import { ARTIFACT_KINDS } from "../types";
import { Badge, Button, fmtTime, useToast } from "../ui";

const KIND_LABEL: Record<ArtifactKind, string> = {
  SARIF: "Static analysis (SARIF)",
  JUNIT: "Test results (JUnit)",
  COVERAGE: "Coverage",
  METADATA: "Changed metadata",
  FINANCIAL: "Financial validation",
  GENERIC: "Generic",
};

const KIND_CLS: Record<ArtifactKind, string> = {
  SARIF: "border-amber-400/40 text-amber-300",
  JUNIT: "border-sky-400/40 text-sky-300",
  COVERAGE: "border-emerald-400/40 text-emerald-300",
  METADATA: "border-violet-400/40 text-violet-300",
  FINANCIAL: "border-bad/50 text-bad",
  GENERIC: "border-line text-ink-dim",
};

function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function ArtifactsPanel({
  storyId,
  actor,
}: {
  storyId: string;
  actor: string;
}) {
  const [kind, setKind] = useState<ArtifactKind | "AUTO">("AUTO");
  const fileRef = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const queryClient = useQueryClient();

  const artifactsQuery = useQuery({
    queryKey: ["artifacts", storyId],
    queryFn: () => api.artifacts(storyId),
  });
  const consumersQuery = useQuery({
    queryKey: ["artifact-consumers"],
    queryFn: api.artifactConsumers,
    staleTime: Infinity,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["artifacts", storyId] });
    queryClient.invalidateQueries({ queryKey: ["timeline", storyId] });
  };

  const upload = useMutation({
    mutationFn: (file: File) =>
      api.uploadArtifact(storyId, file, kind, actor || "unknown"),
    onSuccess: (a) => {
      toast(
        a.parse_error ? "error" : "ok",
        a.parse_error
          ? `Uploaded ${a.filename} but parsing failed: ${a.parse_error}`
          : `Uploaded ${a.filename} — ${a.summary}`,
      );
      if (fileRef.current) fileRef.current.value = "";
      invalidate();
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.deleteArtifact(id, actor || "unknown"),
    onSuccess: () => {
      toast("ok", "Artifact removed");
      invalidate();
    },
    onError: (e: Error) => toast("error", e.message),
  });

  const artifacts = artifactsQuery.data ?? [];
  const consumers = consumersQuery.data?.by_kind ?? {};

  const onPick = () => {
    const file = fileRef.current?.files?.[0];
    if (!file) {
      toast("error", "Choose a file first");
      return;
    }
    if (!actor.trim()) {
      toast("error", "Enter your name in the header — uploads are attributed.");
      return;
    }
    upload.mutate(file);
  };

  return (
    <div className="flex flex-col gap-4 text-xs">
      <div className="rounded-lg border border-line bg-bg/40 p-3">
        <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Upload a CI/CD artifact
        </h3>
        <p className="mb-3 text-[11px] leading-relaxed text-ink-dim">
          Feed the Development &amp; Testing agents real output — SARIF scans, JUnit/
          pytest results, coverage reports, financial validation data, or a changed-
          metadata manifest. Agents analyse the actual data on their next run.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            className="max-w-[240px] text-[11px] text-ink-dim file:mr-2 file:rounded file:border-0 file:bg-panel-2 file:px-2 file:py-1 file:text-ink"
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value as ArtifactKind | "AUTO")}
            className="rounded-md border border-line bg-panel-2 px-2 py-1 text-[11px] text-ink"
          >
            <option value="AUTO">Auto-detect kind</option>
            {ARTIFACT_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </select>
          <Button variant="primary" busy={upload.isPending} onClick={onPick}>
            ↑ Upload
          </Button>
        </div>
        {kind !== "AUTO" && consumers[kind]?.length > 0 && (
          <p className="mt-2 text-[10px] text-ink-faint">
            Consumed by: {consumers[kind].join(", ")}
          </p>
        )}
      </div>

      {artifacts.length === 0 ? (
        <p className="py-6 text-center text-[11px] text-ink-faint">
          No artifacts uploaded for this story yet.
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {artifacts.map((a: Artifact) => (
            <div
              key={a.id}
              className="rounded-lg border border-line bg-panel p-3"
            >
              <div className="flex items-center gap-2">
                <Badge className={KIND_CLS[a.kind]}>{a.kind}</Badge>
                <span className="truncate font-mono text-[11px] text-ink">
                  {a.filename}
                </span>
                <span className="ml-auto font-mono text-[10px] text-ink-faint">
                  {bytes(a.size_bytes)} · {a.uploaded_by} · {fmtTime(a.created_at)}
                </span>
                <button
                  onClick={() => remove.mutate(a.id)}
                  className="text-ink-faint transition-colors hover:text-bad"
                  title="Remove artifact"
                >
                  ✕
                </button>
              </div>
              <p
                className={`mt-1.5 text-[11px] ${a.parse_error ? "text-bad" : "text-ink-dim"}`}
              >
                {a.parse_error ? `Parse error: ${a.parse_error}` : a.summary}
              </p>
              {consumers[a.kind]?.length > 0 && (
                <p className="mt-0.5 text-[10px] text-ink-faint">
                  Feeds: {consumers[a.kind].join(", ")}
                </p>
              )}
              {!a.parse_error && (
                <details className="mt-1.5">
                  <summary className="cursor-pointer text-[10px] text-ink-faint">
                    Parsed data
                  </summary>
                  <pre className="mt-1 max-h-56 overflow-auto rounded border border-line bg-bg p-2 font-mono text-[10px] text-ink-dim">
                    {JSON.stringify(a.parsed, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
