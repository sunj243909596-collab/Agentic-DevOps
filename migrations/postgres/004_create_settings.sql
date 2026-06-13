-- Migration: System settings (key-value)
-- Stores runtime-configurable paths that used to be hardcoded / read from env

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT,
    updated_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_by  TEXT
);

-- Seed default values
INSERT INTO settings (key, value, description) VALUES
    ('git_workspace', '/tmp/devmanager/repos',  '裸克隆 git 仓库存放路径 (per repository_id)'),
    ('git_hunks_dir', '/tmp/devmanager/hunks',  '每次 run 的 diff hunks 临时目录 (per run_id)'),
    ('policy_version', 'v1',                    '策略引擎版本号'),
    ('scoring_version', 'v1',                   '评分引擎版本号')
ON CONFLICT (key) DO NOTHING;

COMMENT ON TABLE settings IS '系统级运行时配置，前端可修改';
