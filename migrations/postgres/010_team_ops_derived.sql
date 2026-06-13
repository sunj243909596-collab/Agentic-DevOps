-- S4 P4 — Derived cache（3 张派生表）
-- 全部可重算；webhook/P3 触发 lazy 重算；M09 提供"全量重算"job
--
-- 设计原则：
-- - 派生表只能从镜像表 (iterations/issues/issue_assignments) + change_units 重算
-- - 不写原表，由 recompute/* 入口统一 UPSERT
-- - 主键 = 维度列 + 时间窗 / iteration_id（无时间窗单值用 computed_at 兜底）

-- ── workload_snapshot：每人 × 时间窗 ───────────────────────────────────────

CREATE TABLE workload_snapshot (
    person_id UUID NOT NULL,
    time_window TEXT NOT NULL,   -- '7d' | '30d' | 'all'
    open_issues INT NOT NULL DEFAULT 0,
    in_progress_issues INT NOT NULL DEFAULT 0,
    completed_issues INT NOT NULL DEFAULT 0,
    estimate_hours_remaining NUMERIC(12, 2) NOT NULL DEFAULT 0,
    estimate_hours_completed NUMERIC(12, 2) NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (person_id, time_window),
    CHECK (time_window IN ('7d', '30d', 'all'))
);

COMMENT ON TABLE workload_snapshot IS
    'S4 P4 — 个人 × 时间窗 工作负载快照（来自 issue_assignment + issues）';
COMMENT ON COLUMN workload_snapshot.time_window IS
    '7d / 30d / all，v1 仅这 3 档';
COMMENT ON COLUMN workload_snapshot.estimate_hours_remaining IS
    'open + in_progress 状态 issue 的 estimate_hours 之和';
COMMENT ON COLUMN workload_snapshot.estimate_hours_completed IS
    'done/closed 状态 issue 的 estimate_hours 之和';

CREATE INDEX idx_workload_snapshot_computed_at
    ON workload_snapshot (computed_at);

-- ── capacity_snapshot：每人 × iteration ────────────────────────────────────

CREATE TABLE capacity_snapshot (
    person_id UUID NOT NULL,
    iteration_id UUID NOT NULL,
    estimated_hours NUMERIC(12, 2) NOT NULL DEFAULT 0,
    weekly_capacity_hours NUMERIC(6, 2) NOT NULL DEFAULT 40.0,
    iteration_weeks INT NOT NULL DEFAULT 2,
    load_ratio NUMERIC(6, 3) NOT NULL DEFAULT 0.0,  -- estimated / (weekly * weeks)
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (person_id, iteration_id),
    FOREIGN KEY (iteration_id) REFERENCES iteration(iteration_id) ON DELETE CASCADE,
    CHECK (load_ratio >= 0),
    CHECK (weekly_capacity_hours > 0),
    CHECK (iteration_weeks > 0)
);

COMMENT ON TABLE capacity_snapshot IS
    'S4 P4 — 个人 × 迭代 容量快照（load_ratio = estimated / available）';
COMMENT ON COLUMN capacity_snapshot.weekly_capacity_hours IS
    '个人周可用工时，v1 默认 40（P5+ 可配置）';
COMMENT ON COLUMN capacity_snapshot.iteration_weeks IS
    '迭代周数，default 2（与 SPEC A6 两周节奏一致）';
COMMENT ON COLUMN capacity_snapshot.load_ratio IS
    'estimated / (weekly * iteration_weeks)；> 1.0 = 满载 / 超载';

CREATE INDEX idx_capacity_snapshot_iteration
    ON capacity_snapshot (iteration_id);

-- ── familiarity_edge：每人 × 代码领域 ─────────────────────────────────────

CREATE TABLE familiarity_edge (
    person_id UUID NOT NULL,
    area_key TEXT NOT NULL,    -- v1: 'lang:<language>' (例: 'lang:python')
    commits_count INT NOT NULL DEFAULT 0,
    lines_changed INT NOT NULL DEFAULT 0,
    score NUMERIC(8, 3) NOT NULL DEFAULT 0.0,  -- log(1+lines) 降权
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (person_id, area_key)
);

COMMENT ON TABLE familiarity_edge IS
    'S4 P4 — 个人 × 代码领域 熟悉度（v1 按编程语言聚合）';
COMMENT ON COLUMN familiarity_edge.area_key IS
    'v1 格式: lang:<language>；v2 可加 path:<dir> / repo:<name>';
COMMENT ON COLUMN familiarity_edge.score IS
    'log10(1 + lines_changed)，做降权避免单一大文件虚高';

CREATE INDEX idx_familiarity_edge_person
    ON familiarity_edge (person_id);
