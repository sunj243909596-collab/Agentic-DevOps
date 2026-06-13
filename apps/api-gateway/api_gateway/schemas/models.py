from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Shared ────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    correlation_id: str | None = None


# ── Repositories ─────────────────────────────────────────────────────────────

class RepositoryResponse(OrmBase):
    repository_id: uuid.UUID
    provider: str
    full_name: str
    clone_url: str | None = None
    status: str
    created_at: datetime


PROVIDER_PATTERN = r"^(github|gitlab|other)$"
RepositoryProvider = str  # 'github' | 'gitlab' | 'other'


# ── Trigger Events ────────────────────────────────────────────────────────────

class TriggerEventIn(BaseModel):
    event_id: uuid.UUID
    event_type: str
    source: str
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$", description="GitLab path_with_namespace 形式，1~N 段，如 owner/repo 或 group/subgroup/repo")
    target_branch: str
    correlation_id: uuid.UUID
    event_timestamp: datetime
    clone_url: str | None = None
    target_sha: str | None = None
    actor: str | None = None
    payload_reference: str | None = None


class TriggerEventOut(BaseModel):
    run_id: uuid.UUID


# ── Analysis Runs ─────────────────────────────────────────────────────────────

class CreateAnalysisRunIn(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$", description="GitLab path_with_namespace 形式，1~N 段，如 owner/repo 或 group/subgroup/repo")
    target_branch: str
    clone_url: str | None = None
    target_sha: str | None = None
    access_token: str | None = None
    provider: str | None = Field(default=None, pattern=PROVIDER_PATTERN)


class AnalysisRunResponse(OrmBase):
    run_id: uuid.UUID
    repository_id: uuid.UUID
    repository_full_name: str
    trigger_id: uuid.UUID | None = None
    trigger_type: str
    target_branch: str
    baseline_sha: str
    target_sha: str
    merge_base_sha: str | None = None
    history_rewrite_detected: bool
    status: str
    policy_version: str
    scoring_version: str
    agent_versions: dict[str, Any]
    failure_reason: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


# ── Change Units ──────────────────────────────────────────────────────────────

class ChangeUnitResponse(OrmBase):
    change_unit_id: uuid.UUID
    run_id: uuid.UUID
    repository_full_name: str
    file_path: str
    previous_file_path: str | None = None
    change_type: str
    language: str
    owner: str | None = None
    added_lines: int
    deleted_lines: int
    is_binary: bool
    is_generated: bool
    is_vendor: bool
    is_test_file: bool
    risk_tags: list[str]
    baseline_sha: str
    target_sha: str


# ── Findings ──────────────────────────────────────────────────────────────────

class FindingResponse(OrmBase):
    finding_id: str
    run_id: uuid.UUID
    category: str
    severity: str
    confidence: float
    repository_full_name: str
    commit_sha: str
    file_path: str
    start_line: int
    end_line: int
    observation: str
    impact: str
    recommendation: str
    verification: str
    evidence_refs: list[str]
    related_knowledge_refs: list[str]
    status: str
    dedupe_key: str | None = None


class FindingStatusUpdateIn(BaseModel):
    status: str = Field(pattern=r"^(accepted|rejected|disputed|resolved)$")
    reason: str = Field(min_length=1)


# ── Score ─────────────────────────────────────────────────────────────────────

class ScoreResponse(OrmBase):
    score_id: uuid.UUID
    run_id: uuid.UUID
    scoring_version: str
    status: str
    final_score: float | None = None
    grade: str | None = None
    confidence: float | None = None
    deductions: list[Any]
    caps: list[str]
    limitations: list[str]
    created_at: datetime


# ── Report ────────────────────────────────────────────────────────────────────

class ReportResponse(OrmBase):
    report_id: uuid.UUID
    run_id: uuid.UUID
    status: str
    content_reference: str
    generated_at: datetime


# ── Audit Events ──────────────────────────────────────────────────────────────

class AuditEventResponse(OrmBase):
    event_id: uuid.UUID
    actor: str
    workflow_id: uuid.UUID | None = None
    event_type: str
    tool: str | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    policy_version: str | None = None
    policy_decision: str | None = None
    event_metadata: dict[str, Any]
    event_timestamp: datetime
    inserted_at: datetime


# ── Publication Requests ──────────────────────────────────────────────────────

class PublicationRequestIn(BaseModel):
    report_id: uuid.UUID
    channel: str
    destination: str
    content_reference: str


class PublicationRequestOut(BaseModel):
    request_id: uuid.UUID
    policy_decision: str
