-- DevManager-Agent MVP initial schema.
-- PostgreSQL 14+ recommended.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE repositories (
    repository_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL CHECK (provider IN ('github', 'gitlab', 'other')),
    full_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    owner_team TEXT,
    policy_id TEXT NOT NULL DEFAULT 'default-readonly',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trigger_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    repository_id UUID REFERENCES repositories(repository_id),
    repository_full_name TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    target_sha TEXT,
    actor TEXT,
    correlation_id UUID NOT NULL,
    payload_reference TEXT,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_timestamp TIMESTAMPTZ NOT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE analysis_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(repository_id),
    trigger_id UUID REFERENCES trigger_events(event_id),
    trigger_type TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    baseline_sha TEXT NOT NULL,
    target_sha TEXT NOT NULL,
    merge_base_sha TEXT,
    history_rewrite_detected BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    agent_versions JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT analysis_runs_sha_format CHECK (
        baseline_sha ~ '^[0-9a-fA-F]{7,64}$'
        AND target_sha ~ '^[0-9a-fA-F]{7,64}$'
    )
);

CREATE INDEX idx_analysis_runs_repo_started ON analysis_runs(repository_id, started_at DESC);
CREATE INDEX idx_analysis_runs_status ON analysis_runs(status);

CREATE TABLE baselines (
    repository_id UUID NOT NULL REFERENCES repositories(repository_id),
    branch TEXT NOT NULL,
    last_successful_sha TEXT NOT NULL CHECK (last_successful_sha ~ '^[0-9a-fA-F]{7,64}$'),
    run_id UUID REFERENCES analysis_runs(run_id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repository_id, branch)
);

CREATE TABLE change_units (
    change_unit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    repository_full_name TEXT NOT NULL,
    baseline_sha TEXT NOT NULL,
    target_sha TEXT NOT NULL,
    file_path TEXT NOT NULL,
    previous_file_path TEXT,
    change_type TEXT NOT NULL CHECK (change_type IN ('added', 'modified', 'deleted', 'renamed', 'copied', 'type_changed')),
    language TEXT NOT NULL,
    owner TEXT,
    added_lines INTEGER NOT NULL DEFAULT 0 CHECK (added_lines >= 0),
    deleted_lines INTEGER NOT NULL DEFAULT 0 CHECK (deleted_lines >= 0),
    is_binary BOOLEAN NOT NULL DEFAULT false,
    is_generated BOOLEAN NOT NULL DEFAULT false,
    is_vendor BOOLEAN NOT NULL DEFAULT false,
    is_test_file BOOLEAN NOT NULL DEFAULT false,
    risk_tags TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    hunks_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_change_units_run ON change_units(run_id);
CREATE INDEX idx_change_units_risk_tags ON change_units USING GIN (risk_tags);

CREATE TABLE review_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    change_unit_ids UUID[] NOT NULL,
    tool_evidence_refs TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    knowledge_context_refs TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    constraints JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_review_tasks_run ON review_tasks(run_id);

CREATE TABLE findings (
    finding_pk UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id TEXT NOT NULL UNIQUE,
    run_id UUID NOT NULL REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low', 'informational')),
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    repository_full_name TEXT NOT NULL,
    commit_sha TEXT NOT NULL CHECK (commit_sha ~ '^[0-9a-fA-F]{7,64}$'),
    file_path TEXT NOT NULL,
    start_line INTEGER NOT NULL CHECK (start_line >= 1),
    end_line INTEGER NOT NULL CHECK (end_line >= 1),
    observation TEXT NOT NULL,
    impact TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    verification TEXT NOT NULL,
    evidence_refs TEXT[] NOT NULL,
    related_knowledge_refs TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'accepted', 'rejected', 'disputed', 'resolved')),
    dedupe_key TEXT,
    raw_agent_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT findings_line_range CHECK (end_line >= start_line),
    CONSTRAINT findings_evidence_required CHECK (array_length(evidence_refs, 1) >= 1)
);

CREATE INDEX idx_findings_run ON findings(run_id);
CREATE INDEX idx_findings_status ON findings(status);
CREATE INDEX idx_findings_severity ON findings(severity);
CREATE INDEX idx_findings_dedupe ON findings(run_id, dedupe_key);

CREATE TABLE scores (
    score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    scoring_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('complete', 'incomplete')),
    final_score NUMERIC(5,2) CHECK (final_score >= 0 AND final_score <= 100),
    grade TEXT CHECK (grade IN ('A+', 'A', 'B', 'C', 'D', 'F')),
    confidence NUMERIC(4,3) CHECK (confidence >= 0 AND confidence <= 1),
    deductions JSONB NOT NULL DEFAULT '[]'::jsonb,
    caps TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    limitations TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reports (
    report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs(run_id) ON DELETE CASCADE,
    report_type TEXT NOT NULL DEFAULT 'daily_markdown',
    status TEXT NOT NULL CHECK (status IN ('generated', 'unavailable')),
    content_reference TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE policy_decisions (
    decision_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES analysis_runs(run_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('allowed', 'denied', 'approval_required')),
    reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    approved_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_policy_decisions_run ON policy_decisions(run_id);

CREATE TABLE audit_events (
    event_id UUID PRIMARY KEY,
    actor TEXT NOT NULL,
    workflow_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    tool TEXT,
    input_ref TEXT,
    output_ref TEXT,
    model_version TEXT,
    prompt_version TEXT,
    policy_version TEXT,
    policy_decision TEXT CHECK (policy_decision IN ('allowed', 'denied', 'approval_required')),
    approval_identity TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    event_timestamp TIMESTAMPTZ NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_events_workflow ON audit_events(workflow_id, event_timestamp DESC);
CREATE INDEX idx_audit_events_type ON audit_events(event_type);

CREATE TABLE finding_status_history (
    history_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_pk UUID NOT NULL REFERENCES findings(finding_pk) ON DELETE CASCADE,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    changed_by TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_finding_status_history_finding ON finding_status_history(finding_pk, changed_at DESC);
