# Contracts

Shared API, event, and data contracts for DevManager-Agent MVP.

## Files

- `schemas/analysis-run.schema.json`: workflow run state and metadata.
- `schemas/trigger-event.schema.json`: normalized trigger events.
- `schemas/change-unit.schema.json`: normalized Git diff units.
- `schemas/review-task.schema.json`: reviewer agent task input.
- `schemas/reviewer-finding.schema.json`: structured reviewer finding output.
- `schemas/score.schema.json`: deterministic scoring output.
- `schemas/audit-event.schema.json`: immutable audit event envelope.
- `schemas/report-publication-request.schema.json`: controlled publication request.
- `openapi.yaml`: MVP HTTP API contract.

## Contract Rules

- All agent outputs must validate against JSON Schema before persistence.
- Every external action request must pass policy validation and audit logging.
- Low-confidence findings do not contribute to score deductions.
- Evidence references must be URI-like strings and resolvable by authorized users.
