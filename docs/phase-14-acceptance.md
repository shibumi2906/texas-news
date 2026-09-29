# Phase 14 acceptance: Advanced Admin / AI Admin

Phase 14 adds portal-scoped AI administration to the existing modular monolith. The Admin UI
manages task routes and budgets, prompt versions, A/B experiments, and operational usage metrics
through the Phase 10 AI service. It does not call AI providers directly.

## Security and isolation

- AI admin endpoints require an authenticated session with the `admin` role.
- Mutations require the existing session-bound CSRF token and origin checks.
- Portal paths scope task settings, prompts, experiments, and usage queries.
- Provider availability is constrained by the server-side Phase 10 allowlist and configured
  provider credentials. Secrets are not accepted from Admin or returned in API responses.
- Task, prompt, and experiment mutations write `EditorialAuditLog` records.

## Data and behavior

- Migration `0015_phase_14_ai_admin` adds portal task configuration and A/B experiment tables,
  and allows portal-scoped prompt definitions while preserving global prompt definitions.
- Routing overrides are consumed by the shared Phase 10 AI service/provider registry.
- Prompt variant selection is deterministic per portal, task, and content identity.
- The dashboard aggregates the portal's prior 30 days of executions, token usage, estimated cost,
  latency, provider/model usage, and errors.
- No Phase 15 advertising or notification functionality is included.

## Verification

The source-level checks and focused frontend/backend tests are recorded in the delivery report. A
database-backed acceptance run requires the local PostgreSQL/Redis Compose runtime; if that runtime
is unavailable, migration execution, integration tests, and runtime smoke remain explicitly
unverified rather than being treated as passing.
