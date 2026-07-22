import type {
  AgentDef,
  AgentInsights,
  Artifact,
  ChallengeReport,
  ConnectorStatus,
  AcAmbiguityDigest,
  ArtifactKind,
  AuditEvent,
  EvalScorecard,
  FlakyLedger,
  FlakySig,
  Gate,
  FlowReport,
  MiPack,
  OpHealth,
  OverrideDigest,
  PipelineView,
  PortfolioTrend,
  PushItem,
  QualityReport,
  ReadinessReport,
  ReleaseSummary,
  SlaBreachReport,
  Worklist,
  ReplayReport,
  RiskEntry,
  RiskRegisterData,
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
  agentOpHealth: () => request<OpHealth>("/insights/agent-health"),
  replayRun: (id: string) => post<ReplayReport>(`/runs/${id}/replay`),
  challenges: (storyId: string, phase: string) =>
    request<ChallengeReport>(`/stories/${storyId}/challenges?phase=${phase}`),

  riskRegister: (storyId?: string) =>
    request<RiskRegisterData>(`/risk-register${storyId ? `?story_id=${storyId}` : ""}`),
  reviewRisk: (id: string, actor: string, note: string) =>
    post<RiskEntry>(`/risk-register/${id}/review`, { actor, note }),
  closeRisk: (id: string, actor: string, note: string) =>
    post<RiskEntry>(`/risk-register/${id}/close`, { actor, note }),

  releases: () => request<ReleaseSummary[]>("/reports/releases"),
  createRelease: (actor: string, name: string, target_date: string, story_ids: string[]) =>
    post<{ id: string; name: string }>("/reports/releases", { actor, name, target_date, story_ids }),
  setReleaseStories: (id: string, actor: string, story_ids: string[]) =>
    post<{ id: string }>(`/reports/releases/${id}/stories`, { actor, story_ids }),
  miPreview: (id: string) => request<MiPack>(`/reports/releases/${id}/mi-preview`),
  sealMi: (id: string, actor: string) =>
    post<{ snapshot_id: string; payload_hash: string }>(`/reports/releases/${id}/seal-mi`, { actor }),
  portfolioTrend: () => request<PortfolioTrend>("/reports/portfolio-trend"),
  flowReport: () => request<FlowReport>("/reports/flow"),
  qualityReport: () => request<QualityReport>("/reports/quality"),
  worklist: (storyId: string) => request<Worklist>(`/reports/worklist/${storyId}`),
  slaBreaches: () => request<SlaBreachReport>("/reports/sla-breaches"),
  readiness: () => request<ReadinessReport>("/reports/readiness"),
  acAmbiguity: () => request<AcAmbiguityDigest>("/reports/ac-ambiguity"),
  overrides: (assignee?: string) =>
    request<OverrideDigest>(`/reports/overrides${assignee ? `?assignee=${encodeURIComponent(assignee)}` : ""}`),

  evalScorecard: () => request<EvalScorecard>("/insights/eval-scorecard"),
  flakyTests: () => request<FlakyLedger>("/insights/flaky-tests"),
  quarantineFlaky: (id: string, actor: string, owner: string, expiry_days: number, note: string) =>
    post<FlakySig>(`/insights/flaky-tests/${id}/quarantine`, { actor, owner, expiry_days, note }),
  clearFlaky: (id: string, actor: string, note: string) =>
    post<FlakySig>(`/insights/flaky-tests/${id}/clear`, { actor, note }),

  // CI/CD connectors
  copadoStatus: () => request<ConnectorStatus>("/copado/status"),
  copadoSimulate: (jira_key: string, environment: string) =>
    post<{ ingested: { kind: string; summary: string }[] }>("/copado/simulate", {
      jira_key,
      environment,
    }),
  githubStatus: () => request<ConnectorStatus>("/github/status"),
  githubConnect: (story_id: string, repo: string, branch: string, actor: string) =>
    post<{ github_repo: string; github_branch: string }>("/github/connect", {
      story_id,
      repo,
      branch,
      actor,
    }),
  githubSync: (story_id: string, actor: string) =>
    post<{ ingested: { kind: string; summary: string }[] }>("/github/sync", {
      story_id,
      actor,
    }),

  stories: () => request<StoryBoard[]>("/stories"),
  story: (id: string) => request<StoryDetail>(`/stories/${id}`),
  health: (id: string) => request<StoryHealth>(`/stories/${id}/health`),
  pipeline: (id: string) => request<PipelineView>(`/stories/${id}/pipeline`),
  timeline: (id: string) => request<AuditEvent[]>(`/stories/${id}/timeline`),
  refreshStory: (id: string) => post<StoryDetail>(`/stories/${id}/refresh`),
  gates: (storyId: string) => request<Gate[]>(`/stories/${storyId}/gates`),

  approveRun: (id: string, approver: string) =>
    post<Run>(`/runs/${id}/approve`, { approver }),
  acceptRun: (id: string, actor: string, reason = "") =>
    post<Run>(`/runs/${id}/accept`, { actor, reason }),
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
