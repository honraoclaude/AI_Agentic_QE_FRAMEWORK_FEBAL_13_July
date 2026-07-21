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

export interface RiskEntry {
  id: string;
  story_id: string;
  jira_key: string;
  source: string;
  agent_key: string | null;
  phase: string;
  severity: string;
  title: string;
  detail: string;
  accepted_by: string;
  rationale: string;
  accepted_at: string | null;
  review_by: string | null;
  status: "OPEN" | "REVIEWED" | "CLOSED";
  overdue: boolean;
  reviewed_by: string | null;
  review_note: string;
  closed_by: string | null;
  closure_note: string;
}

export interface RiskRegisterData {
  entries: RiskEntry[];
  summary: {
    total: number;
    open: number;
    overdue: number;
    by_severity: Record<string, number>;
  };
}

export interface FlakySig {
  id: string;
  ref: string;
  signature: string;
  test_name: string;
  normalized_message: string;
  occurrences: number;
  flaky_votes: number;
  stories_seen: string[];
  runs_seen: number;
  first_seen: string | null;
  last_seen: string | null;
  flake_score: number;
  status: "WATCH" | "QUARANTINED" | "CLEARED";
  owner: string | null;
  quarantine_expiry: string | null;
  quarantine_expired: boolean;
  note: string;
}

export interface FlakyLedger {
  signatures: FlakySig[];
  summary: {
    total: number;
    quarantined: number;
    expired_quarantines: number;
    high_score: number;
  };
}

// ---- Stakeholder reporting ----

export interface ReleaseSummary {
  id: string;
  name: string;
  target_date: string;
  status: string;
  story_ids: string[];
  snapshots: {
    id: string;
    kind: string;
    payload_hash: string;
    generated_by: string;
    created_at: string | null;
  }[];
}

export interface MiPack {
  release: { id: string; name: string; target_date: string; status: string; stories: number };
  generated_at: string;
  confidence_index: number | null;
  bands: Record<string, number>;
  stories: {
    jira_key: string;
    summary: string;
    phase: string;
    released: boolean;
    score: number | null;
    band: string;
    blockers: number;
    inconsistencies: number;
  }[];
  quality_debt: { open: number; overdue: number; by_severity: Record<string, number> };
  regulatory_evidence: {
    stories_with_fca_evidence_complete: number;
    fca_scenarios_unexecuted: number;
    financial_checks: number;
    financial_checks_failed: number;
  };
  ai_governance: {
    runs_executed: number;
    human_decided_pct: number | null;
    override_rate: number | null;
    first_time_right_rate: number | null;
  };
  flow: {
    stories_released: number;
    avg_lead_time_days: number | null;
    rework_story_rate: number | null;
  };
}

export interface FlowReport {
  generated_at: string;
  gate_cycle_times: { phase: string; avg_days: number; gates: number }[];
  hitl_queue: {
    depth: number;
    runs: { kind: string; jira_key: string; agent: string; age_days: number }[];
    gates_ready: { jira_key: string; phase: string; age_days: number }[];
    avg_decision_latency_days: number | null;
  };
  blocking_questions: { jira_key: string; question: string; owner: string; age_days: number }[];
}

export interface QualityReport {
  generated_at: string;
  traceability: {
    jira_key: string;
    ac_total: number;
    covered: number;
    partial: number;
    not_covered: number;
  }[];
  uncovered_example_cards: number;
  test_pyramid: { unit: number; api: number; ui: number };
  first_time_right: {
    agent_key: string;
    agent_name: string;
    accepted: number;
    first_time_right_rate: number;
  }[];
  flake_index: {
    total: number;
    quarantined: number;
    expired_quarantines: number;
    high_score: number;
  };
}

export interface Worklist {
  story_id: string;
  generated_at: string;
  items: {
    agent_key: string;
    agent_name: string;
    phase: string;
    severity: string;
    title: string;
    detail: string;
    run_status: string;
  }[];
  counts: Record<string, number>;
}

export interface SlaBreachReport {
  generated_at: string;
  thresholds: Record<string, number>;
  breaches: {
    kind: string;
    jira_key: string;
    agent: string | null;
    phase: string;
    age_days: number;
    threshold_days: number;
    over_by_days: number;
  }[];
  summary: { total: number; by_phase: Record<string, number> };
}

export interface ReadinessReport {
  generated_at: string;
  stories: {
    jira_key: string;
    summary: string;
    phase: string;
    score: number | null;
    band: string;
    blockers: number;
    open_risks: number;
    overdue_risks: number;
    target_date: string | null;
    days_to_target: number | null;
    scope_risk: "LOW" | "MEDIUM" | "HIGH";
  }[];
  summary: { total: number; high_risk: number; medium_risk: number };
}

export interface AcAmbiguityDigest {
  generated_at: string;
  stories: {
    jira_key: string;
    phase: string;
    escalate: boolean;
    blocking: { question: string; owner: string | null }[];
    non_blocking: { question: string; owner: string | null }[];
  }[];
  summary: {
    stories_with_open_questions: number;
    stories_blocking: number;
    escalations: number;
  };
}

export interface OverrideDigest {
  generated_at: string;
  assignee: string | null;
  agents: {
    agent_key: string;
    agent_name: string;
    count: number;
    items: {
      jira_key: string;
      kind: "REJECTED" | "RERUN_GUIDANCE";
      reason: string;
      decided_at: string | null;
    }[];
  }[];
  summary: { total_overrides: number };
}

export interface EvalScorecard {
  agents: {
    agent_key: string;
    agent_name: string;
    cases: number;
    passed: number;
    failed: number;
    failing_cases: {
      case: string;
      failing_checks: { path: string; expected: unknown; actual: unknown; passed: boolean }[];
    }[];
  }[];
  summary: {
    agents_with_golden_data: number;
    agents_total: number;
    coverage_percent: number;
    total_cases: number;
    total_passed: number;
    total_failed: number;
  };
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
