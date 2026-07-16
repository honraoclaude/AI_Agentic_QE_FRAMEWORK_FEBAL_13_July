import type {
  AgentDef,
  AgentInsights,
  Artifact,
  ArtifactKind,
  AuditEvent,
  Gate,
  PushItem,
  Run,
  SettingsView,
  StoryBoard,
  StoryDetail,
  StoryHealth,
  SyncResult,
  WorkQueue,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

const post = <T,>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined });

export const api = {
  agentInsights: () => request<AgentInsights>("/insights/agents"),
  stories: () => request<StoryBoard[]>("/stories"),
  story: (id: string) => request<StoryDetail>(`/stories/${id}`),
  health: (id: string) => request<StoryHealth>(`/stories/${id}/health`),
  timeline: (id: string) => request<AuditEvent[]>(`/stories/${id}/timeline`),
  refreshStory: (id: string) => post<StoryDetail>(`/stories/${id}/refresh`),
  gates: (storyId: string) => request<Gate[]>(`/stories/${storyId}/gates`),

  approveRun: (id: string, approver: string) =>
    post<Run>(`/runs/${id}/approve`, { approver }),
  acceptRun: (id: string, actor: string) => post<Run>(`/runs/${id}/accept`, { actor }),
  rejectRun: (id: string, actor: string, reason: string) =>
    post<Run>(`/runs/${id}/reject`, { actor, reason }),
  rerunRun: (id: string, actor: string, guidance: string) =>
    post<Run>(`/runs/${id}/rerun`, { actor, guidance }),

  signoffGate: (id: string, approver_name: string, approver_role: string, rationale: string) =>
    post<Gate>(`/gates/${id}/signoff`, { approver_name, approver_role, rationale }),
  rejectGate: (id: string, approver_name: string, approver_role: string, rationale: string) =>
    post<Gate>(`/gates/${id}/reject`, { approver_name, approver_role, rationale }),

  sync: (actor: string) => post<SyncResult>("/jira/sync", { actor }),
  testConnection: () => post<Record<string, unknown>>("/jira/test-connection"),
  seedDemo: () => post<SyncResult>("/demo/seed"),

  pushQueue: (storyId?: string) =>
    request<PushItem[]>(`/push${storyId ? `?story_id=${storyId}` : ""}`),
  draftPush: (kind: "agent_summary" | "bdd_scenarios", run_id: string, actor: string) =>
    post<PushItem>("/push/draft", { kind, run_id, actor }),
  approvePush: (id: string, actor: string) => post<PushItem>(`/push/${id}/approve`, { actor }),
  retryPush: (id: string, actor: string) => post<PushItem>(`/push/${id}/retry`, { actor }),

  audit: (params: Record<string, string>) =>
    request<AuditEvent[]>(`/audit?${new URLSearchParams(params)}`),
  auditVerify: () => request<{ valid: boolean; events?: number }>("/audit/verify"),

  agents: () => request<AgentDef[]>("/agents"),

  artifacts: (storyId: string) =>
    request<Artifact[]>(`/stories/${storyId}/artifacts`),
  artifactConsumers: () =>
    request<{ by_kind: Record<string, string[]> }>("/artifacts/consumers"),
  uploadArtifact: async (
    storyId: string,
    file: File,
    kind: ArtifactKind | "AUTO",
    uploadedBy: string,
  ): Promise<Artifact> => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("uploaded_by", uploadedBy || "unknown");
    const res = await fetch(`${BASE}/stories/${storyId}/artifacts`, {
      method: "POST",
      body: form, // browser sets multipart Content-Type + boundary
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        detail = (await res.json()).detail;
      } catch {
        /* non-JSON */
      }
      throw new ApiError(res.status, detail);
    }
    return res.json() as Promise<Artifact>;
  },
  deleteArtifact: (id: string, actor: string) =>
    request<{ ok: boolean }>(`/artifacts/${id}?actor=${encodeURIComponent(actor)}`, {
      method: "DELETE",
    }),

  work: (role: string) =>
    request<WorkQueue>(`/work?role=${encodeURIComponent(role)}`),

  settings: () => request<SettingsView>("/settings"),
  updateSettings: (actor: string, patch: Record<string, unknown>) =>
    request<SettingsView>("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actor, patch }),
    }),
};
