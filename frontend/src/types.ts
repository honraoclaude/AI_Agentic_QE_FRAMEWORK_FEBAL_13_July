// Mirrors backend/app/schemas — keep in sync by hand for v1.

export type Phase = "REFINEMENT" | "DEVELOPMENT" | "TESTING" | "RELEASE";
export const PHASES: Phase[] = ["REFINEMENT", "DEVELOPMENT", "TESTING", "RELEASE"];

export const ROLES = [
  "Product Owner",
  "Tech Lead",
  "QE Lead",
  "Business Stakeholder",
  "Compliance Officer",
] as const;
export type Role = (typeof ROLES)[number];

export type WorkKind =
  | "GATE_SIGNOFF"
  | "RUN_APPROVAL"
  | "RUN_DECISION"
  | "PUSH_APPROVAL"
  | "PUSH_RETRY";

export interface WorkItem {
  kind: WorkKind;
  action: "SIGN_GATE" | "APPROVE_RUN" | "DECIDE_RUN" | "APPROVE_PUSH" | "RETRY_PUSH";
  story_id: string;
  jira_key: string;
  story_summary: string;
  phase: Phase | null;
  entity_id: string;
  title: string;
  detail: string;
  reason: string;
  since: string | null;
}

export interface WorkQueue {
  role: Role;
  roles: Role[];
  items: WorkItem[];
  counts: Partial<Record<WorkKind, number>>;
}

export type RunStatus =
  | "PROPOSED"
  | "AWAITING_APPROVAL"
  | "RUNNING"
  | "COMPLETED"
  | "ACCEPTED"
  | "REJECTED"
  | "RERUN_REQUESTED"
  | "SKIPPED"
  | "FAILED";

export type GateStatus = "LOCKED" | "READY_FOR_SIGNOFF" | "SIGNED_OFF" | "REJECTED";
export type PushStatus = "DRAFT" | "APPROVED" | "SENT" | "FAILED" | "RETRYING";

export interface RunSummary {
  id: string;
  agent_key: string;
  phase: Phase;
  sequence: number;
  attempt: number;
  status: RunStatus;
}

export interface Run extends RunSummary {
  story_id: string;
  prompt_version: string;
  model: string | null;
  input_hash: string | null;
  input_json: Record<string, unknown> | null;
  output_json: Record<string, unknown> | null;
  output_hash: string | null;
  token_usage: { input_tokens?: number; output_tokens?: number } | null;
  guidance: string | null;
  parent_run_id: string | null;
  approved_by: string | null;
  decided_by: string | null;
  decision_reason: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  decided_at: string | null;
}

export interface Gate {
  id: string;
  story_id: string;
  phase: Phase;
  status: GateStatus;
  approver_name: string | null;
  approver_role: string | null;
  rationale: string | null;
  evidence: { accepted_runs?: Array<Record<string, unknown>> } | null;
  created_at: string;
  decided_at: string | null;
}

export interface StoryBase {
  id: string;
  jira_key: string;
  summary: string;
  description: string | null;
  acceptance_criteria: string[];
  story_points: number | null;
  sprint: string | null;
  jira_status: string | null;
  assignee: string | null;
  labels: string[];
  priority: string | null;
  fca_impact: "LOW" | "MEDIUM" | "HIGH" | null;
  fca_impact_confirmed: boolean;
  cloud: "FSC" | "SALES" | "MARKETING" | null;
  current_phase: Phase;
  scope_status: "ACTIVE" | "OUT_OF_SCOPE";
  released: boolean;
  copado_user_story_id: string | null;
  github_repo: string | null;
  github_branch: string | null;
  jira_updated_at: string | null;
  last_synced_at: string | null;
  changed_since_agent_run: boolean;
}

export interface ConnectorStatus {
  ok: boolean;
  demo_mode: boolean;
  configured: boolean;
}

export interface StoryBoard extends StoryBase {
  runs: RunSummary[];
  gates: Gate[];
}

export interface StoryDetail extends StoryBase {
  runs: Run[];
  gates: Gate[];
}

export interface AuditEvent {
  id: number;
  event_type: string;
  entity_type: string;
  entity_id: string;
  actor: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  event_hash: string;
  created_at: string;
}

export interface PushItem {
  id: string;
  story_id: string;
  push_type: "COMMENT" | "LABEL" | "TRANSITION" | "ATTACHMENT";
  status: PushStatus;
  payload: Record<string, unknown> & { preview_text?: string; jira_key?: string; kind?: string };
  approved_by: string | null;
  attempts: number;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentDef {
  key: string;
  name: string;
  phase: Phase;
  sequence: number;
  pact: string[];
  purpose: string;
  model_role: string;
  blocking_capable: boolean;
  prompt_version: string;
}

export type ArtifactKind =
  | "SARIF"
  | "JUNIT"
  | "COVERAGE"
  | "METADATA"
  | "FINANCIAL"
  | "GENERIC";

export const ARTIFACT_KINDS: ArtifactKind[] = [
  "SARIF",
  "JUNIT",
  "COVERAGE",
  "METADATA",
  "FINANCIAL",
  "GENERIC",
];

export interface AgentPerf {
  agent_key: string;
  agent_name: string;
  phase: string;
  accepted: number;
  rejected: number;
  reruns: number;
  decided: number;
  acceptance_rate: number | null;
  override_rate: number;
  trust_score: number | null;
  avg_attempts: number | null;
  verdicts: { PASS: number; WARN: number; FAIL: number };
  reject_reasons: string[];
  guidance_samples: string[];
}

export interface AgentInsights {
  agents: AgentPerf[];
  summary: {
    agents_defined: number;
    agents_with_data: number;
    total_accepted: number;
    total_rejected: number;
    total_reruns: number;
    overall_acceptance_rate: number | null;
  };
  needs_attention: AgentPerf[];
}

export interface Inconsistency {
  rule: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  agents: string[];
  detail: string;
  recommendation: string;
}

export interface StoryHealth {
  score: number | null;
  band: "HEALTHY" | "AT_RISK" | "CRITICAL" | "BLOCKED" | "NO_DATA";
  assurance: "HIGH" | "MEDIUM" | "LOW" | null;
  counts: { pass: number; warn: number; fail: number };
  phase_breakdown: { phase: string; score: number }[];
  blockers: { agent: string; phase: string; summary: string }[];
  least_confident: { agent: string; verdict: string; phase: string }[];
  worst_finding_severity: string | null;
  agents_evaluated: number;
  inconsistencies: Inconsistency[];
  inconsistency_count: number;
}

export interface ReplayReport {
  run_id: string;
  agent_key: string;
  status: "REPRODUCED" | "INPUT_DRIFT" | "OUTPUT_DIVERGED";
  input_match: boolean;
  output_match: boolean;
  drift: string[];
  original_input_hash: string;
  replay_input_hash: string;
  original_output_hash: string;
  replay_output_hash: string;
  verdict_stable: boolean;
  original_verdict: string | null;
  replay_verdict: string | null;
  model: string;
  deterministic: boolean;
}

export interface AgentOpHealth {
  agent_key: string;
  agent_name: string;
  phase: string;
  current_prompt_version: string;
  executed: number;
  failed: number;
  failure_rate: number;
  avg_duration_s: number | null;
  max_duration_s: number | null;
  tokens_in: number;
  tokens_out: number;
  versions: { version: string; executed: number; failed: number; failure_rate: number }[];
}

export interface OpHealth {
  agents: AgentOpHealth[];
  alerts: { agent_key: string; agent_name: string; kind: string; detail: string }[];
  summary: {
    agents_with_runs: number;
    total_executed: number;
    total_failed: number;
    total_tokens_in: number;
    total_tokens_out: number;
  };
}

export interface Challenge {
  kind: string;
  agent_key: string;
  agent_name: string;
  challenge: string;
  basis: string;
}

export interface ChallengeReport {
  story_id: string;
  phase: string;
  challenges: Challenge[];
  count: number;
  generated_by: string;
  note: string;
}

export interface PipelineNode {
  key: string;
  name: string;
  phase: Phase;
  sequence: number;
  blocking_capable: boolean;
  status: RunStatus | null;
  attempt: number;
  run_id: string | null;
  verdict: string | null;
  confidence: string | null;
  release_blocking: boolean;
}

export interface PipelineEdge {
  source: string;
  target: string;
  kind: "upstream" | "artifact";
}

export interface PipelineView {
  story_id: string;
  jira_key: string;
  current_phase: Phase;
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  sources: { id: string; kinds: string[] }[];
  gates: Record<string, { id: string; status: GateStatus }>;
}

export interface Artifact {
  id: string;
  story_id: string;
  kind: ArtifactKind;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  parsed: Record<string, unknown>;
  summary: string;
  parse_error: string | null;
  raw_excerpt: string | null;
  uploaded_by: string;
  source: "MANUAL" | "COPADO" | "GITHUB";
  source_ref: string | null;
  created_at: string;
}

export interface SyncResult {
  total: number;
  created: number;
  updated: number;
  unchanged: number;
  out_of_scope: number;
  flagged_conflicts: string[];
}

export interface SettingsView {
  env: {
    demo_mode: boolean;
    jira_base_url: string;
    jira_email: string;
    jira_api_token_set: boolean;
    anthropic_api_key_set: boolean;
    reasoning_model: string;
    classification_model: string;
  };
  settings: {
    jira: { project_key: string; board_id: number; jql_override: string };
    platform: { base_url: string };
    field_mappings: Record<string, unknown>;
    gates: Record<
      string,
      {
        auto_post_comment: boolean;
        apply_label: boolean;
        label: string;
        transition_name: string | null;
        attach_evidence?: boolean;
      }
    >;
    sync: { enabled: boolean; interval_minutes: number };
    agents: { disabled: string[] };
  };
}
