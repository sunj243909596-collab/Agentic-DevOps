export enum TriggerType {
  ScheduledDaily = 'scheduled.daily',
  Manual = 'manual',
  GitPush = 'git.push',
  PullRequest = 'pull_request',
  CiCompleted = 'ci.completed',
  ObservabilityAlert = 'observability.alert',
}

export enum RunStatus {
  TriggerReceived = 'trigger_received',
  Authorized = 'authorized',
  BaselineResolved = 'baseline_resolved',
  RepositoryFetched = 'repository_fetched',
  DiffExtracted = 'diff_extracted',
  DataSanitized = 'data_sanitized',
  ChangeClassified = 'change_classified',
  ReviewsDispatched = 'reviews_dispatched',
  FindingsAggregated = 'findings_aggregated',
  FindingsValidated = 'findings_validated',
  ScoreCalculated = 'score_calculated',
  PolicyEvaluated = 'policy_evaluated',
  ReportGenerated = 'report_generated',
  BaselineCommitted = 'baseline_committed',
  Completed = 'completed',
  PartialAnalysis = 'partial_analysis',
  Failed = 'failed',
  Rejected = 'rejected',
}

export enum ChangeType {
  Added = 'added',
  Modified = 'modified',
  Deleted = 'deleted',
  Renamed = 'renamed',
  Copied = 'copied',
  TypeChanged = 'type_changed',
}

export enum RiskTag {
  Authentication = 'authentication',
  Authorization = 'authorization',
  PublicApi = 'public-api',
  DataMigration = 'data-migration',
  SchemaChange = 'schema-change',
  Transaction = 'transaction',
  Concurrency = 'concurrency',
  Dependency = 'dependency',
  Infrastructure = 'infrastructure',
  Deployment = 'deployment',
  MissingTests = 'missing-tests',
  HighComplexity = 'high-complexity',
  IncidentRelated = 'incident-related',
}

export enum ReviewCategory {
  Correctness = 'correctness',
  Security = 'security',
  Testing = 'testing',
  Reliability = 'reliability',
  Architecture = 'architecture',
  Maintainability = 'maintainability',
  Performance = 'performance',
  Infrastructure = 'infrastructure',
  KbCompliance = 'kb_compliance',
}

export enum Severity {
  Critical = 'critical',
  High = 'high',
  Medium = 'medium',
  Low = 'low',
  Informational = 'informational',
}

export enum FindingStatus {
  Open = 'open',
  Accepted = 'accepted',
  Rejected = 'rejected',
  Disputed = 'disputed',
  Resolved = 'resolved',
}

export enum ScoreStatus {
  Complete = 'complete',
  Incomplete = 'incomplete',
}

export enum Grade {
  APlus = 'A+',
  A = 'A',
  B = 'B',
  C = 'C',
  D = 'D',
  F = 'F',
}

export enum AuditEventType {
  WorkflowTransition = 'workflow.transition',
  ToolInvocation = 'tool.invocation',
  ModelInvocation = 'model.invocation',
  PolicyDecision = 'policy.decision',
  ApprovalDecision = 'approval.decision',
  ReportGenerated = 'report.generated',
}

export enum PolicyDecisionValue {
  Allowed = 'allowed',
  Denied = 'denied',
  ApprovalRequired = 'approval_required',
}

export enum PublicationChannel {
  InternalMarkdown = 'internal_markdown',
  PullRequestComment = 'pull_request_comment',
  Issue = 'issue',
  Slack = 'slack',
  Feishu = 'feishu',
  Dashboard = 'dashboard',
}

export interface Repository {
  repository_id: string;
  provider: 'github' | 'gitlab' | 'other';
  full_name: string;
  default_branch: string;
  owner_team?: string | null;
  policy_id: string;
  status: 'active' | 'disabled' | 'archived';
  created_at: string;
  updated_at: string;
}

export interface TriggerEvent {
  event_id: string;
  event_type: TriggerType;
  source: string;
  timestamp: string;
  repository: string;
  target_branch: string;
  target_sha?: string | null;
  actor?: string | null;
  correlation_id: string;
  payload_reference?: string | null;
}

export interface AnalysisRun {
  run_id: string;
  repository_id: string;
  trigger_id?: string | null;
  trigger_type: TriggerType;
  target_branch: string;
  baseline_sha: string;
  target_sha: string;
  merge_base_sha?: string | null;
  history_rewrite_detected?: boolean;
  status: RunStatus;
  policy_version: string;
  scoring_version: string;
  agent_versions?: Record<string, string>;
  failure_reason?: string | null;
  started_at: string;
  completed_at?: string | null;
}

export interface Baseline {
  repository_id: string;
  branch: string;
  last_successful_sha: string;
  run_id?: string | null;
  updated_at: string;
}

export interface ChangeUnit {
  change_unit_id: string;
  run_id: string;
  repository: string;
  baseline_sha: string;
  target_sha: string;
  file_path: string;
  previous_file_path?: string | null;
  change_type: ChangeType;
  language: string;
  owner?: string | null;
  added_lines: number;
  deleted_lines: number;
  is_binary?: boolean;
  is_generated?: boolean;
  is_vendor?: boolean;
  is_test_file?: boolean;
  risk_tags: RiskTag[];
  hunks_ref?: string | null;
}

export interface ReviewTaskConstraints {
  max_findings: number;
  require_line_evidence: boolean;
  external_actions_allowed: false;
}

export interface ReviewTask {
  task_id: string;
  run_id: string;
  category: ReviewCategory;
  change_unit_ids: string[];
  tool_evidence_refs?: string[];
  knowledge_context_refs?: string[];
  constraints: ReviewTaskConstraints;
}

export interface ReviewerFinding {
  finding_id: string;
  run_id: string;
  category: ReviewCategory;
  severity: Severity;
  confidence: number;
  repository: string;
  commit_sha: string;
  file: string;
  start_line: number;
  end_line: number;
  observation: string;
  impact: string;
  recommendation: string;
  verification: string;
  evidence_refs: string[];
  related_knowledge_refs?: string[];
  status: FindingStatus;
  dedupe_key?: string | null;
}

export interface ScoreDeduction {
  finding_id: string;
  category: ReviewCategory | string;
  severity: Severity | string;
  raw_deduction: number;
  adjusted_deduction: number;
  cap_applied?: string | null;
}

export interface Score {
  score_id: string;
  run_id: string;
  scoring_version: string;
  status: ScoreStatus;
  final_score?: number | null;
  grade?: Grade | null;
  confidence?: number | null;
  deductions: ScoreDeduction[];
  caps?: string[];
  limitations?: string[];
  created_at: string;
}

export interface PolicyDecision {
  decision_id: string;
  run_id?: string | null;
  action: string;
  decision: PolicyDecisionValue;
  reason: string;
  policy_version: string;
  approved_by?: string | null;
  created_at: string;
}

export interface AuditEvent {
  event_id: string;
  actor: string;
  workflow_id: string;
  event_type: AuditEventType;
  tool?: string | null;
  input_ref?: string | null;
  output_ref?: string | null;
  model_version?: string | null;
  prompt_version?: string | null;
  policy_version?: string | null;
  policy_decision?: PolicyDecisionValue | null;
  approval_identity?: string | null;
  metadata?: Record<string, unknown>;
  timestamp: string;
}

export interface ReportPublicationRequest {
  request_id: string;
  report_id: string;
  channel: PublicationChannel;
  destination: string;
  approval_required: boolean;
  content_reference: string;
  policy_version: string;
}
