-- M3: add clone_url to repositories for git ingestion
ALTER TABLE repositories ADD COLUMN IF NOT EXISTS clone_url TEXT;
