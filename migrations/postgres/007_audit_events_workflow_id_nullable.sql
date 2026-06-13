-- 007: Allow audit_events.workflow_id to be NULL
-- Reason: when an analysis run is deleted, we preserve the audit trail
-- (GSP 05805 — audit trail is non-negotiable) by keeping audit_events
-- rows and nulling out their workflow_id. The previous schema declared
-- workflow_id NOT NULL, which made DELETE /analysis-runs/{run_id} fail
-- with a NotNullViolationError. The existing composite index
-- idx_audit_events_workflow continues to work (PG indexes NULL values
-- in btree by default) and the query paths filtering on workflow_id
-- simply skip orphan rows, which is the correct behaviour.
ALTER TABLE audit_events
    ALTER COLUMN workflow_id DROP NOT NULL;
