-- Migration: Add access_token to repositories table
-- For HTTPS GitLab clone with PAT authentication

ALTER TABLE repositories
ADD COLUMN access_token VARCHAR(512);

COMMENT ON COLUMN repositories.access_token IS 'GitLab Personal Access Token for HTTPS clone (stored encrypted in production)';
