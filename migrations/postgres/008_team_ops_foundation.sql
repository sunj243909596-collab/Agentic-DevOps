-- 008_team_ops_foundation.sql
-- S4 P1: Team Operations — Foundation 5 张表
--   team / person / team_membership / gitlab_identity / pm_identity
--
-- 风格沿用 001_initial_schema.sql：
--   - UUID PK 用 gen_random_uuid()（pgcrypto）
--   - 时间戳 TIMESTAMPTZ DEFAULT now()
--   - 枚举值用 CHECK 约束
--   - 索引在表后建
--
-- 唯一性策略：
--   - team.name UNIQUE
--   - person.email UNIQUE
--   - 身份表（gitlab/pm）的"当前唯一"用部分唯一索引 WHERE effective_to IS NULL

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── team ─────────────────────────────────────────────────────────────────────

CREATE TABLE team (
    team_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── person ───────────────────────────────────────────────────────────────────

CREATE TABLE person (
    person_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive', 'archived')),
    data_access_scope TEXT NOT NULL DEFAULT 'self'
        CHECK (data_access_scope IN ('self', 'team_lead', 'platform_admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_person_status ON person(status);

-- ── team_membership (junction) ───────────────────────────────────────────────

CREATE TABLE team_membership (
    team_id UUID NOT NULL REFERENCES team(team_id) ON DELETE CASCADE,
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('member', 'lead', 'admin')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    left_at TIMESTAMPTZ,
    PRIMARY KEY (team_id, person_id),
    CONSTRAINT team_membership_left_after_joined
        CHECK (left_at IS NULL OR left_at >= joined_at)
);

CREATE INDEX idx_team_membership_person ON team_membership(person_id);
CREATE INDEX idx_team_membership_active
    ON team_membership(team_id) WHERE left_at IS NULL;

-- ── gitlab_identity ──────────────────────────────────────────────────────────

CREATE TABLE gitlab_identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    gitlab_user_id BIGINT NOT NULL,
    gitlab_username TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    CONSTRAINT gitlab_identity_dates
        CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX idx_gitlab_identity_person ON gitlab_identity(person_id);
-- 一个 GitLab user 同一时刻只允许一个 active 映射（effective_to IS NULL）
CREATE UNIQUE INDEX uq_gitlab_identity_active_user
    ON gitlab_identity(gitlab_user_id) WHERE effective_to IS NULL;

-- ── pm_identity ───────────────────────────────────────────────────────────────

CREATE TABLE pm_identity (
    identity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_id UUID NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
    pm_user_id TEXT NOT NULL,
    pm_username TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ,
    CONSTRAINT pm_identity_dates
        CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE INDEX idx_pm_identity_person ON pm_identity(person_id);
CREATE UNIQUE INDEX uq_pm_identity_active_user
    ON pm_identity(pm_user_id) WHERE effective_to IS NULL;
