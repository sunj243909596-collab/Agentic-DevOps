-- 006: LLM base_url (for self-hosted or proxied Claude endpoints)
-- Empty value = use provider default (https://api.anthropic.com for claude).
INSERT INTO settings (key, value, description) VALUES
    ('llm_base_url', '',
     'Custom API base URL for the LLM provider. Leave empty to use the provider default. Useful for self-hosted / proxied / Azure / Bedrock-compatible endpoints.')
ON CONFLICT (key) DO NOTHING;
