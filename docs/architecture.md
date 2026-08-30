# Platform architecture through Phase 2

The Site Platform begins as a modular monolith in one monorepo:

- `apps/api` owns backend application logic and infrastructure adapters.
- `apps/web` is a server-capable Next.js frontend and is not authoritative for business rules.
- `packages/shared` is reserved for intentionally shared contracts.
- PostgreSQL is the future authoritative persistent store.
- Redis is limited to ephemeral infrastructure concerns.
- The `worker` Compose service is an infrastructure-only process skeleton. It verifies connectivity and waits for shutdown; it registers no jobs from later phases.

Phase 1 adds explicit `portals`, `geography`, `taxonomy`, `entities`, `content`, and `media` module boundaries. Each exposes domain, application, infrastructure, and API layers as needed. The API layers intentionally expose no HTTP content surface yet; repositories and application services provide the Phase 1 operations.

Phase 2 adds an `ingestion` module with domain contracts/models, an application service, PostgreSQL repository, exact-body HMAC verification, Redis-backed rate limiting, and an internal API boundary. `IncomingPackage` owns stable package identity and the latest pointer; every `IncomingPackageVersion` is immutable and retains the validated canonical payload. Package acceptance and Site-domain mapping share one database transaction.

`NEWS_INTEGRATOR_INTERFACE.md` remains authoritative for the Integrator-to-Site boundary. Schema 1.0 and additive 1.1 are accepted; other versions are rejected before persistence. Duplicate bytes are acknowledged idempotently, conflicting immutable bytes fail, and unseen older replay versions are retained without moving the latest pointer or regressing `ContentItem`.

Source package versions map to independent Site `ContentVersion.version_number` values and retain the upstream package number in `source_revision`. Typed current-domain data is mapped where the wire contract is deterministic. Language variants, AI provenance, legacy regions, and insufficiently typed entity data are preserved in the immutable payload/metadata for their owning later phases.

The Site does not implement Integrator retries, replay control APIs, delivery DLQ, media downloading, publication, or editorial workflows in Phase 2.
