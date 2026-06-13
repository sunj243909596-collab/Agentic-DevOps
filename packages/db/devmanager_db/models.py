from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"

    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    default_branch: Mapped[str] = mapped_column(Text, nullable=False, default="main")
    owner_team: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_id: Mapped[str] = mapped_column(Text, nullable=False, default="default-readonly")
    clone_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('github', 'gitlab', 'other')", name="ck_repositories_provider",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled', 'archived')", name="ck_repositories_status",
        ),
    )


class TriggerEvent(Base):
    __tablename__ = "trigger_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    repository_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.repository_id"), nullable=True
    )
    repository_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    target_branch: Mapped[str] = mapped_column(Text, nullable=False)
    target_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.repository_id"), nullable=False
    )
    trigger_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trigger_events.event_id"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_branch: Mapped[str] = mapped_column(Text, nullable=False)
    repository_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_sha: Mapped[str] = mapped_column(Text, nullable=False)
    target_sha: Mapped[str] = mapped_column(Text, nullable=False)
    merge_base_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    history_rewrite_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    agent_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_analysis_runs_repo_started", "repository_id", "started_at"),
        Index("idx_analysis_runs_status", "status"),
    )


class Baseline(Base):
    __tablename__ = "baselines"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.repository_id"), primary_key=True
    )
    branch: Mapped[str] = mapped_column(Text, primary_key=True)
    last_successful_sha: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.run_id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChangeUnit(Base):
    __tablename__ = "change_units"

    change_unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    repository_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    baseline_sha: Mapped[str] = mapped_column(Text, nullable=False)
    target_sha: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    previous_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_lines: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_binary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_vendor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_test_file: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_tags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    hunks_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_change_units_run", "run_id"),)


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    change_unit_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False,
    )
    tool_evidence_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    knowledge_context_refs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list,
    )
    constraints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_review_tasks_run", "run_id"),)


class Finding(Base):
    __tablename__ = "findings"

    finding_pk: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    finding_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.run_id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    repository_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    commit_sha: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    verification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    related_knowledge_refs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list,
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    dedupe_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_agent_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_findings_run", "run_id"),
        Index("idx_findings_status", "status"),
        Index("idx_findings_severity", "severity"),
        Index("idx_findings_dedupe", "run_id", "dedupe_key"),
    )


class FindingStatusHistory(Base):
    __tablename__ = "finding_status_history"

    history_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    finding_pk: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("findings.finding_pk", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_status: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_finding_status_history_finding", "finding_pk", "changed_at"),)


class Score(Base):
    __tablename__ = "scores"

    score_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    scoring_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    final_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    grade: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    deductions: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    caps: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    limitations: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Report(Base):
    __tablename__ = "reports"

    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    report_type: Mapped[str] = mapped_column(Text, nullable=False, default="daily_markdown")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    content_reference: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_runs.run_id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("idx_policy_decisions_run", "run_id"),)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: when the associated analysis run is deleted we keep the
    # audit row (GSP 05805) and null out workflow_id instead of cascading.
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    tool: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_identity: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict,
    )
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("idx_audit_events_workflow", "workflow_id", "event_timestamp"),
        Index("idx_audit_events_type", "event_type"),
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── S4 P1: Team Operations — Foundation ─────────────────────────────────────


class Team(Base):
    __tablename__ = "team"

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Person(Base):
    __tablename__ = "person"

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    data_access_scope: Mapped[str] = mapped_column(Text, nullable=False, default="self")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')", name="ck_person_status"
        ),
        CheckConstraint(
            "data_access_scope IN ('self', 'team_lead', 'platform_admin')",
            name="ck_person_data_access_scope",
        ),
        Index("idx_person_status", "status"),
    )


class TeamMembership(Base):
    __tablename__ = "team_membership"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("team.team_id", ondelete="CASCADE"),
        primary_key=True,
    )
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.person_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "role IN ('member', 'lead', 'admin')", name="ck_team_membership_role"
        ),
        Index("idx_team_membership_person", "person_id"),
    )


class GitlabIdentity(Base):
    __tablename__ = "gitlab_identity"

    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.person_id", ondelete="CASCADE"),
        nullable=False,
    )
    gitlab_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gitlab_username: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_gitlab_identity_person", "person_id"),)


class PmIdentity(Base):
    __tablename__ = "pm_identity"

    identity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.person_id", ondelete="CASCADE"),
        nullable=False,
    )
    pm_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    pm_username: Mapped[str] = mapped_column(Text, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_pm_identity_person", "person_id"),)


# ── S4 P2: Team Operations — Mirror 4 张表 ───────────────────────────────────


class Iteration(Base):
    __tablename__ = "iteration"

    iteration_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pm_iteration_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    pm_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pm_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('planning', 'active', 'completed', 'cancelled')",
            name="ck_iteration_status",
        ),
        Index("idx_iteration_status", "status"),
        Index("idx_iteration_dates", "start_date", "end_date"),
    )


class Issue(Base):
    __tablename__ = "issue"

    issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pm_issue_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    issue_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    estimate_hours: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    iteration_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iteration.iteration_id", ondelete="SET NULL"),
        nullable=True,
    )
    pm_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pm_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "issue_type IN ('story', 'task', 'bug', 'epic', 'subtask')",
            name="ck_issue_type",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')", name="ck_issue_priority"
        ),
        Index("idx_issue_iteration", "iteration_id"),
        Index("idx_issue_status", "status"),
        Index("idx_issue_priority", "priority"),
        Index("idx_issue_pm_updated", "pm_updated_at"),
    )


class IssueAssignment(Base):
    __tablename__ = "issue_assignment"

    assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    issue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue.issue_id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("person.person_id", ondelete="SET NULL"),
        nullable=True,
    )
    pm_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    pm_username: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('assignee', 'reporter', 'watcher', 'mentioned')",
            name="ck_issue_assignment_role",
        ),
        UniqueConstraint(
            "issue_id", "pm_user_id", "role", name="uq_issue_assignment_identity"
        ),
        Index("idx_issue_assignment_issue", "issue_id"),
        Index("idx_issue_assignment_person", "person_id"),
        Index("idx_issue_assignment_pm_user", "pm_user_id"),
    )


class MrReviewEvent(Base):
    __tablename__ = "mr_review_event"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mr_iid: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    author_gitlab_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    author_pm_user_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_branch: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "action IN ('opened', 'merged', 'closed', 'reviewed', 'approved', "
            "'changes_requested', 'commented')",
            name="ck_mr_review_event_action",
        ),
        Index(
            "uq_mr_review_event_idem",
            "project_id", "mr_iid", "action", "event_created_at",
            unique=True,
        ),
        Index("idx_mr_review_event_project", "project_id"),
        Index("idx_mr_review_event_author_gl", "author_gitlab_user_id"),
        Index("idx_mr_review_event_author_pm", "author_pm_user_id"),
        Index("idx_mr_review_event_action_time", "action", "event_created_at"),
    )


class PmSyncCursor(Base):
    """S4 P3 — PM 平台增量同步水位线（每资源 1 行）。

    source_key 形如 'pm:iterations' / 'pm:issues' / 'pm:assignments' / 'pm:users'。
    cursor_value 是 PM 平台返回的游标或 last_updated_at ISO8601 字符串。
    首次同步为 NULL（视为全量）。
    """

    __tablename__ = "pm_sync_cursor"

    source_key: Mapped[str] = mapped_column(Text, primary_key=True)
    cursor_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


# ── S4 P4 — Derived cache (3 张派生表) ─────────────────────────────────────


class WorkloadSnapshot(Base):
    """S4 P4 — 个人 × 时间窗 工作负载快照。

    来源：issue_assignment LEFT JOIN issues 聚合。
    time_window ∈ {'7d', '30d', 'all'}，v1 仅这 3 档。
    """

    __tablename__ = "workload_snapshot"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    time_window: Mapped[str] = mapped_column(Text, primary_key=True)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    in_progress_issues: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    completed_issues: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    estimate_hours_remaining: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    estimate_hours_completed: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "time_window IN ('7d', '30d', 'all')",
            name="ck_workload_snapshot_window",
        ),
        Index("idx_workload_snapshot_computed_at", "computed_at"),
    )


class CapacitySnapshot(Base):
    """S4 P4 — 个人 × 迭代 容量快照。

    来源：capacity 来自 setting（v1 写死 40h/周）；
    estimated 来自该 person 在该 iteration 的 issue_assignment × issue.estimate_hours。
    load_ratio = estimated / (weekly_capacity_hours * iteration_weeks)。
    """

    __tablename__ = "capacity_snapshot"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    iteration_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iteration.iteration_id", ondelete="CASCADE"),
        primary_key=True,
    )
    estimated_hours: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0
    )
    weekly_capacity_hours: Mapped[float] = mapped_column(
        Numeric(6, 2), nullable=False, default=40.0
    )
    iteration_weeks: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    load_ratio: Mapped[float] = mapped_column(
        Numeric(6, 3), nullable=False, default=0.0
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint("load_ratio >= 0", name="ck_capacity_load_ratio_nonneg"),
        CheckConstraint(
            "weekly_capacity_hours > 0", name="ck_capacity_weekly_positive"
        ),
        CheckConstraint("iteration_weeks > 0", name="ck_capacity_weeks_positive"),
        Index("idx_capacity_snapshot_iteration", "iteration_id"),
    )


class FamiliarityEdge(Base):
    """S4 P4 — 个人 × 代码领域 熟悉度。

    v1 area_key 形如 'lang:python'，score = log10(1 + lines_changed) 降权。
    来源：change_units JOIN 某种 person 解析（v1 用 owner 字符串与 person.display_name 匹配）。
    """

    __tablename__ = "familiarity_edge"

    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    area_key: Mapped[str] = mapped_column(Text, primary_key=True)
    commits_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lines_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Numeric(8, 3), nullable=False, default=0.0)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (Index("idx_familiarity_edge_person", "person_id"),)


# ── S4 P5 — Suggestion / Feedback / WebhookIdempotency (3 张表) ─────────────


class Suggestion(Base):
    """S4 P5 — 建议占位容器（v1 仅存不生成）。

    严守 PRD 边界：payload 只含"事实 + 趋势"，不出现"应该 / 必须 / 建议 / 推荐"语言。
    source_refs 是引用 source row（workload_snapshot、iteration、mr_review_event 等）。
    """

    __tablename__ = "suggestion"

    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    suggestion_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    source_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "target_type IN ('team', 'person', 'iteration', 'issue')",
            name="ck_suggestion_target_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'viewed', 'accepted', 'dismissed', 'expired')",
            name="ck_suggestion_status",
        ),
        Index("idx_suggestion_target", "target_type", "target_id"),
        Index("idx_suggestion_type", "suggestion_type"),
        Index("idx_suggestion_status", "status"),
        Index("idx_suggestion_valid", "valid_from", "valid_to"),
    )


class SuggestionFeedback(Base):
    """S4 P5 — 用户对建议的反馈流水。"""

    __tablename__ = "suggestion_feedback"

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True
    )
    suggestion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("suggestion.suggestion_id", ondelete="CASCADE"),
        nullable=False,
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_type: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "feedback_type IN ('viewed', 'accepted', 'dismissed', 'commented')",
            name="ck_suggestion_feedback_type",
        ),
        Index("idx_suggestion_feedback_suggestion", "suggestion_id"),
        Index("idx_suggestion_feedback_actor", "actor"),
    )


class WebhookIdempotency(Base):
    """S4 P5 — Webhook 幂等去重表（P6 GitLab webhook 实际使用）。

    idempotency_key 形如 "gitlab:<event_uuid>" 或 "pm:<event_id>"。
    """

    __tablename__ = "webhook_idempotency"

    idempotency_key: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="received")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "source IN ('gitlab', 'pm')", name="ck_webhook_idempotency_source",
        ),
        CheckConstraint(
            "status IN ('received', 'processed', 'failed')",
            name="ck_webhook_idempotency_status",
        ),
        Index("idx_webhook_idempotency_source_received", "source", "received_at"),
    )


# ── Phase 7.4 — Knowledge Base (pgvector RAG) ────────────────────────────────


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_document"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    repository: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("source", "title", "version", name="uq_knowledge_doc_ver"),
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunk"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_document.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(1536), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_idx"),
    )

