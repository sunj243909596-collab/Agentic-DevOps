-- S4 P5 — Suggestion + SuggestionFeedback + WebhookIdempotency (3 张表)
-- Suggestion 是 S3 规划域的"占位容器"（v1 不生成，只存）
-- WebhookIdempotency 是 P6 GitLab webhook 去重（提前到 P5 落库）

-- ── suggestion：占位容器 ────────────────────────────────────────────────────

CREATE TABLE suggestion (
    suggestion_id UUID PRIMARY KEY,
    target_type TEXT NOT NULL,           -- 'team' | 'person' | 'iteration' | 'issue'
    target_id UUID NOT NULL,
    suggestion_type TEXT NOT NULL,       -- 'sprint_planning' | 'task_assignment' | 'priority' | 'growth'
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '{}'::jsonb,  -- 引用 source rows（仅事实化，无 "should"）
    status TEXT NOT NULL DEFAULT 'pending',
    valid_from TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMPTZ,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (status IN ('pending', 'viewed', 'accepted', 'dismissed', 'expired')),
    CHECK (target_type IN ('team', 'person', 'iteration', 'issue'))
);

COMMENT ON TABLE suggestion IS
    'S4 P5 — 建议占位容器（v1 仅存不生成；P3/S3 由策略模块写入）';
COMMENT ON COLUMN suggestion.target_type IS
    '建议作用对象类型：team / person / iteration / issue';
COMMENT ON COLUMN suggestion.suggestion_type IS
    '建议类别：sprint_planning / task_assignment / priority / growth';
COMMENT ON COLUMN suggestion.payload IS
    '结构化建议内容（事实 + 趋势），符合 packages/contracts 中 Suggestion schema';
COMMENT ON COLUMN suggestion.source_refs IS
    '来源数据 row 引用（如 workload_snapshot、iteration），用于"事实化"防线';
COMMENT ON COLUMN suggestion.status IS
    'pending / viewed / accepted / dismissed / expired';

CREATE INDEX idx_suggestion_target ON suggestion (target_type, target_id);
CREATE INDEX idx_suggestion_type ON suggestion (suggestion_type);
CREATE INDEX idx_suggestion_status ON suggestion (status);
CREATE INDEX idx_suggestion_valid ON suggestion (valid_from, valid_to);

-- ── suggestion_feedback：人对建议的反馈（点击 / 接受 / 驳回） ─────────────

CREATE TABLE suggestion_feedback (
    feedback_id UUID PRIMARY KEY,
    suggestion_id UUID NOT NULL,
    actor TEXT NOT NULL,                -- 反馈者（username / person_id）
    feedback_type TEXT NOT NULL,         -- 'viewed' | 'accepted' | 'dismissed' | 'commented'
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (suggestion_id) REFERENCES suggestion(suggestion_id) ON DELETE CASCADE,
    CHECK (feedback_type IN ('viewed', 'accepted', 'dismissed', 'commented'))
);

COMMENT ON TABLE suggestion_feedback IS
    'S4 P5 — 用户对建议的反馈流水（用于 v2 模型质量评估）';
COMMENT ON COLUMN suggestion_feedback.actor IS
    '反馈者：v1 用 username 字符串（governance 流程 v2 替换为 person_id）';

CREATE INDEX idx_suggestion_feedback_suggestion
    ON suggestion_feedback (suggestion_id);
CREATE INDEX idx_suggestion_feedback_actor
    ON suggestion_feedback (actor);

-- ── webhook_idempotency：P6 GitLab webhook 去重（P5 落库，P6 使用） ───────

CREATE TABLE webhook_idempotency (
    idempotency_key TEXT PRIMARY KEY,    -- 形如 "gitlab:<event_uuid>" 或 "pm:<event_id>"
    source TEXT NOT NULL,                -- 'gitlab' | 'pm'
    event_type TEXT NOT NULL,            -- e.g. 'Merge Request Hook'
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'received',  -- 'received' | 'processed' | 'failed'
    error_message TEXT,
    CHECK (source IN ('gitlab', 'pm')),
    CHECK (status IN ('received', 'processed', 'failed'))
);

COMMENT ON TABLE webhook_idempotency IS
    'S4 P5 — Webhook 幂等去重（P6 实际使用）';
COMMENT ON COLUMN webhook_idempotency.idempotency_key IS
    '事件唯一键（GitLab 用 X-Gitlab-Event-UUID；PM 平台 v2 用业务键）';
COMMENT ON COLUMN webhook_idempotency.status IS
    'received / processed / failed';

CREATE INDEX idx_webhook_idempotency_source_received
    ON webhook_idempotency (source, received_at);
