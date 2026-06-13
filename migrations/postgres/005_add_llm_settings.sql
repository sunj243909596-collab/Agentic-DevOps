-- Migration: LLM provider configuration
-- These keys are managed through 系统设置 → LLM in the UI
-- llm_api_key is stored ENCRYPTED (Fernet) — never plaintext

INSERT INTO settings (key, value, description) VALUES
    ('llm_provider',  'mock',     'LLM provider: claude | mock (add more in devmanager_llm)'),
    ('llm_api_key',   '',         'API key for the active provider (encrypted at rest)'),
    ('llm_model',     'mock-noop','Model name passed to the provider; e.g. claude-sonnet-4-6')
ON CONFLICT (key) DO NOTHING;
