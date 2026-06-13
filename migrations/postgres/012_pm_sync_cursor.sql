-- S4 P3 — pm_sync_cursor (增量同步水位线)
-- 仅控制面元数据，1 表 3 列，迁移独立于 team-ops 14 表
--
-- 用途：记录 PM 平台增量同步的 last_updated_at / last_sync_at
-- 写入者：pm-integration sync/incremental.py
-- 读取者：pm-integration sync/incremental.py
--
-- 字段：
--   source_key: 'pm:iterations' | 'pm:issues' | 'pm:assignments' | 'pm:users'
--   cursor_value: tsquery / cursor str / NULL（首次跑）
--   last_synced_at: 服务端时间戳

CREATE TABLE pm_sync_cursor (
    source_key TEXT PRIMARY KEY,
    cursor_value TEXT,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE pm_sync_cursor IS
    'S4 P3 — PM 平台增量同步水位线（每资源 1 行）';
COMMENT ON COLUMN pm_sync_cursor.source_key IS
    '资源标识，如 pm:iterations / pm:issues / pm:assignments / pm:users';
COMMENT ON COLUMN pm_sync_cursor.cursor_value IS
    'PM 平台游标 / last_updated_at ISO8601 / NULL（首次全量）';
COMMENT ON COLUMN pm_sync_cursor.last_synced_at IS
    '最后一次同步成功时间';
