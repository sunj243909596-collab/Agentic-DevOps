-- Migration: Denormalize repository_full_name into analysis_runs
-- Avoids joins on every run fetch; populated at creation time

ALTER TABLE analysis_runs
ADD COLUMN repository_full_name TEXT;

UPDATE analysis_runs ar
SET repository_full_name = r.full_name
FROM repositories r
WHERE ar.repository_id = r.repository_id;

ALTER TABLE analysis_runs
ALTER COLUMN repository_full_name SET NOT NULL;

COMMENT ON COLUMN analysis_runs.repository_full_name IS 'Denormalized from repositories.full_name at run creation time';
