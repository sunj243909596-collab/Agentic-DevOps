from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TriggerType(StrEnum):
    SCHEDULED_DAILY = "scheduled.daily"
    MANUAL = "manual"
    GIT_PUSH = "git.push"
    PULL_REQUEST = "pull_request"
    CI_COMPLETED = "ci.completed"
    OBSERVABILITY_ALERT = "observability.alert"


class RunStatus(StrEnum):
    TRIGGER_RECEIVED = "trigger_received"
    AUTHORIZED = "authorized"
    BASELINE_RESOLVED = "baseline_resolved"
    REPOSITORY_FETCHED = "repository_fetched"
    DIFF_EXTRACTED = "diff_extracted"
    DATA_SANITIZED = "data_sanitized"
    CHANGE_CLASSIFIED = "change_classified"
    REVIEWS_DISPATCHED = "reviews_dispatched"
    FINDINGS_AGGREGATED = "findings_aggregated"
    FINDINGS_VALIDATED = "findings_validated"
    SCORE_CALCULATED = "score_calculated"
    POLICY_EVALUATED = "policy_evaluated"
    REPORT_GENERATED = "report_generated"
    BASELINE_COMMITTED = "baseline_committed"
    COMPLETED = "completed"
    PARTIAL_ANALYSIS = "partial_analysis"
    FAILED = "failed"
    REJECTED = "rejected"


class ChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"


class RiskTag(StrEnum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    PUBLIC_API = "public-api"
    DATA_MIGRATION = "data-migration"
    SCHEMA_CHANGE = "schema-change"
    TRANSACTION = "transaction"
    CONCURRENCY = "concurrency"
    DEPENDENCY = "dependency"
    INFRASTRUCTURE = "infrastructure"
    DEPLOYMENT = "deployment"
    MISSING_TESTS = "missing-tests"
    HIGH_COMPLEXITY = "high-complexity"
    INCIDENT_RELATED = "incident-related"


class ReviewCategory(StrEnum):
    CORRECTNESS = "correctness"
    SECURITY = "security"
    TESTING = "testing"
    RELIABILITY = "reliability"
    ARCHITECTURE = "architecture"
    MAINTAINABILITY = "maintainability"
    PERFORMANCE = "performance"
    INFRASTRUCTURE = "infrastructure"
    KB_COMPLIANCE = "kb_compliance"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    RESOLVED = "resolved"


class ScoreStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class Grade(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class AuditEventType(StrEnum):
    WORKFLOW_TRANSITION = "workflow.transition"
    TOOL_INVOCATION = "tool.invocation"
    MODEL_INVOCATION = "model.invocation"
    POLICY_DECISION = "policy.decision"
    APPROVAL_DECISION = "approval.decision"
    REPORT_GENERATED = "report.generated"


class PolicyDecisionValue(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"


class PublicationChannel(StrEnum):
    INTERNAL_MARKDOWN = "internal_markdown"
    PULL_REQUEST_COMMENT = "pull_request_comment"
    ISSUE = "issue"
    SLACK = "slack"
    FEISHU = "feishu"
    DASHBOARD = "dashboard"


@dataclass(frozen=True)
class Repository:
    repository_id: str
    provider: str
    full_name: str
    default_branch: str
    policy_id: str
    status: str
    created_at: str
    updated_at: str
    owner_team: str | None = None


@dataclass(frozen=True)
class TriggerEvent:
    event_id: str
    event_type: TriggerType
    source: str
    timestamp: str
    repository: str
    target_branch: str
    correlation_id: str
    target_sha: str | None = None
    actor: str | None = None
    payload_reference: str | None = None


@dataclass(frozen=True)
class AnalysisRun:
    run_id: str
    repository_id: str
    trigger_type: TriggerType
    target_branch: str
    baseline_sha: str
    target_sha: str
    status: RunStatus
    policy_version: str
    scoring_version: str
    started_at: str
    trigger_id: str | None = None
    merge_base_sha: str | None = None
    history_rewrite_detected: bool = False
    agent_versions: dict[str, str] = field(default_factory=dict)
    failure_reason: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class Baseline:
    repository_id: str
    branch: str
    last_successful_sha: str
    updated_at: str
    run_id: str | None = None


@dataclass(frozen=True)
class ChangeUnit:
    change_unit_id: str
    run_id: str
    repository: str
    baseline_sha: str
    target_sha: str
    file_path: str
    change_type: ChangeType
    language: str
    added_lines: int
    deleted_lines: int
    risk_tags: list[RiskTag]
    previous_file_path: str | None = None
    owner: str | None = None
    is_binary: bool = False
    is_generated: bool = False
    is_vendor: bool = False
    is_test_file: bool = False
    hunks_ref: str | None = None


@dataclass(frozen=True)
class ReviewTaskConstraints:
    max_findings: int
    require_line_evidence: bool
    external_actions_allowed: bool = False


@dataclass(frozen=True)
class ReviewTask:
    task_id: str
    run_id: str
    category: ReviewCategory
    change_unit_ids: list[str]
    constraints: ReviewTaskConstraints
    tool_evidence_refs: list[str] = field(default_factory=list)
    knowledge_context_refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewerFinding:
    finding_id: str
    run_id: str
    category: ReviewCategory
    severity: Severity
    confidence: float
    repository: str
    commit_sha: str
    file: str
    start_line: int
    end_line: int
    observation: str
    impact: str
    recommendation: str
    verification: str
    evidence_refs: list[str]
    status: FindingStatus
    related_knowledge_refs: list[str] = field(default_factory=list)
    dedupe_key: str | None = None


@dataclass(frozen=True)
class ScoreDeduction:
    finding_id: str
    category: str
    severity: str
    raw_deduction: float
    adjusted_deduction: float
    cap_applied: str | None = None


@dataclass(frozen=True)
class Score:
    score_id: str
    run_id: str
    scoring_version: str
    status: ScoreStatus
    deductions: list[ScoreDeduction]
    created_at: str
    final_score: float | None = None
    grade: Grade | None = None
    confidence: float | None = None
    caps: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicyDecision:
    decision_id: str
    action: str
    decision: PolicyDecisionValue
    reason: str
    policy_version: str
    created_at: str
    run_id: str | None = None
    approved_by: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    actor: str
    workflow_id: str
    event_type: AuditEventType
    timestamp: str
    tool: str | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    policy_decision: PolicyDecisionValue | None = None
    approval_identity: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportPublicationRequest:
    request_id: str
    report_id: str
    channel: PublicationChannel
    destination: str
    approval_required: bool
    content_reference: str
    policy_version: str
