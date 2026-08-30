# Phase 0 architecture

The Site Platform begins as a modular monolith in one monorepo:

- `apps/api` owns backend application logic and infrastructure adapters.
- `apps/web` is a server-capable Next.js frontend and is not authoritative for business rules.
- `packages/shared` is reserved for intentionally shared contracts.
- PostgreSQL is the future authoritative persistent store.
- Redis is limited to ephemeral infrastructure concerns.
- The `worker` Compose service is an infrastructure-only process skeleton. It verifies connectivity and waits for shutdown; it registers no jobs from later phases.

No Phase 1 domain modules, ingestion receiver, publication logic, AI integration, feeds, users, or editorial features exist in this phase.

`NEWS_INTEGRATOR_INTERFACE.md` schema 1.1 is the authoritative future Integrator-to-Site boundary. The older illustrative contract in `SPEC.md` is not implemented or duplicated.
