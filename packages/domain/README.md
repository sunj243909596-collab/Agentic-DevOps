# Domain Models

Shared DevManager-Agent domain models for TypeScript, Python, and Java.

The models mirror the MVP contracts in `packages/contracts/schemas` and are intentionally framework-light:

- TypeScript uses enums and interfaces.
- Python uses `dataclasses` and `Enum` from the standard library.
- Java uses records and enums.

## Naming

External contracts use snake_case to match JSON Schema and API payloads. These domain models preserve those names where practical so serialization remains direct and predictable.

## Model Groups

- Analysis workflow: `AnalysisRun`, `TriggerEvent`, `Baseline`.
- Change analysis: `ChangeUnit`, `ReviewTask`.
- Review results: `ReviewerFinding`, `FindingStatus`.
- Scoring: `Score`, `ScoreDeduction`.
- Governance: `PolicyDecision`, `AuditEvent`, `ReportPublicationRequest`.
