-- 009_team_ops_mirror.sql
-- S4 P2: Team Operations — Mirror 4 张表
--   iteration / issue / issue_assignment / mr_review_event
--
-- 设计要点：
--   - 镜像表只读，pm-integration / GitLab webhook 是唯一写入路径
--   - PM 字段以 pm_ 前缀（pm_iteration_id / pm_issue_id / pm_user_id）
--   - 双时间戳：pm_created_at/pm_updated_at（PM 端时间）+ last_synced_at（我方同步时间）
--   - mr_review_event 不带 pm_ 前缀（GitLab 来源）；raw_payload 留底

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── iteration ────────────────────────────────────────────────────────────────

CREATE TABLE iteration (
    iteration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pm_iteration_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('planning', 'active', 'completed', 'cancelled')),
    pm_created_at TIMESTAMPTZ,
    pm_updated_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT iteration_date_range CHECK (end_date >= start_date)
);

CREATE INDEX idx_iteration_status ON iteration(status);
CREATE INDEX idx_iteration_dates ON iteration(start_date, end_date);

-- ── issue ────────────────────────────────────────────────────────────────────

CREATE TABLE issue (
    issue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pm_issue_id TEXT NOT NULL UNIQUE,
    issue_key TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    issue_type TEXT NOT NULL CHECK (issue_type IN ('story', 'task', 'bug', 'epic', 'subtask')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    estimate_hours NUMERIC(6, 2) CHECK (estimate_hours IS NULL OR estimate_hours >= 0),
    status TEXT NOT NULL,
    iteration_id UUID REFERENCES iteration(iteration_id) ON DELETE SET NULL,
    pm_created_at TIMESTAMPTZ,
    pm_updated_at TIMESTAMPTZ,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_issue_iteration ON issue(iteration_id);
CREATE INDEX idx_issue_status ON issue(status);
CREATE INDEX idx_issue_priority ON issue(priority);
CREATE INDEX idx_issue_pm_updated ON issue(pm_updated_at);

-- ── issue_assignment ────────────────────────────────────────────────────────

CREATE TABLE issue_assignment (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issue(issue_id) ON DELETE CASCADE,
    person_id UUID REFERENCES person(person_id) ON DELETE SET NULL,  -- 可空：未映射的 PM 用户
    pm_user_id TEXT NOT NULL,
    pm_username TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('assignee', 'reporter', 'watcher', 'mentioned')),
    weight NUMERIC(4, 3) NOT NULL DEFAULT 1.000 CHECK (weight >= 0 AND weight <= 1),
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issue_id, pm_user_id, role)
);

CREATE INDEX idx_issue_assignment_issue ON issue_assignment(issue_id);
CREATE INDEX idx_issue_assignment_person ON issue_assignment(person_id);
CREATE INDEX idx_issue_assignment_pm_user ON issue_assignment(pm_user_id);

-- ── mr_review_event ──────────────────────────────────────────────────────────

CREATE TABLE mr_review_event (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id BIGINT NOT NULL,
    mr_iid BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN (
        'opened', 'merged', 'closed', 'reviewed', 'approved', 'changes_requested', 'commented'
    )),
    author_gitlab_user_id BIGINT,
    author_pm_user_id TEXT,
    target_sha TEXT,
    source_branch TEXT,
    target_branch TEXT,
    title TEXT,
    event_created_at TIMESTAMPTZ NOT NULL,
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 幂等去重：同一 MR 同一 action 同一时间算同一事件
CREATE UNIQUE INDEX uq_mr_review_event_idem
    ON mr_review_event(project_id, mr_iid, action, event_created_at);
CREATE INDEX idx_mr_review_event_project ON mr_review_event(project_id);
CREATE INDEX idx_mr_review_event_author_gl ON mr_review_event(author_gitlab_user_id);
CREATE INDEX idx_mr_review_event_author_pm ON mr_review_event(author_pm_user_id);
CREATE INDEX idx_mr_review_event_action_time ON mr_review_event(action, event_created_at);
