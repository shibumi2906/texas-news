# Platform architecture through Phase 3

The Site Platform begins as a modular monolith in one monorepo:

- `apps/api` owns backend application logic and infrastructure adapters.
- `apps/web` is a server-capable Next.js frontend and is not authoritative for business rules.
- `packages/shared` is reserved for intentionally shared contracts.
- PostgreSQL is the future authoritative persistent store.
- Redis is limited to ephemeral infrastructure concerns.
- The `worker` Compose service runs only the Phase 3 scheduled-publication poller after verifying PostgreSQL and Redis connectivity.

Phase 1 adds explicit `portals`, `geography`, `taxonomy`, `entities`, `content`, and `media` module boundaries. Each exposes domain, application, infrastructure, and API layers as needed. The API layers intentionally expose no HTTP content surface yet; repositories and application services provide the Phase 1 operations.

Phase 2 adds an `ingestion` module with domain contracts/models, an application service, PostgreSQL repository, exact-body HMAC verification, Redis-backed rate limiting, and an internal API boundary. `IncomingPackage` owns stable package identity and the latest pointer; every `IncomingPackageVersion` is immutable and retains the validated canonical payload. Package acceptance and Site-domain mapping share one database transaction.

`NEWS_INTEGRATOR_INTERFACE.md` remains authoritative for the Integrator-to-Site boundary. Schema 1.0 and additive 1.1 are accepted; other versions are rejected before persistence. Duplicate bytes are acknowledged idempotently, conflicting immutable bytes fail, and unseen older replay versions are retained without moving the latest pointer or regressing `ContentItem`.

Source package versions map to independent Site `ContentVersion.version_number` values and retain the upstream package number in `source_revision`. Typed current-domain data is mapped where the wire contract is deterministic. Language variants, AI provenance, legacy regions, and insufficiently typed entity data are preserved in the immutable payload/metadata for their owning later phases.

Phase 3 adds the `editorial` module without changing the Integrator wire contract. `ContentItem.upstream_status` preserves the latest source lifecycle independently from its editorial `status`. Active upstream retraction or deletion prevents scheduling, publishing, or restoration; incoming tombstones remain historically stored. Editorial changes create new `ContentVersion` rows with `origin=editorial`, while source-derived versions use `origin=source`. Historical versions are never updated.

Editorial commands lock their `ContentItem` row and persist the state change, optional new version, and `EditorialAuditLog` in one transaction. Ingestion now acquires the same row lock before mapping a later upstream version. Once `has_editorial_override` is set, upstream updates preserve the editor's current title, subtitle, description, and body while still preserving the full incoming version and refreshing source provenance and associations. Integrator `content.lead` is the source-side value mapped to Site `subtitle`.

The internal `/api/v1/admin/content` API provides only the operations needed for this workflow. `X-Editorial-Actor` supplies audit attribution but is intentionally not a security boundary; authentication and authorization belong to Phase 8. Before/after JSONB snapshots contain editorial state, not secrets.

Scheduled publication is represented directly on `ContentItem`. The existing worker selects due rows in bounded batches with `FOR UPDATE SKIP LOCKED` and calls the same publication rules used by manual commands. It rechecks title/version/upstream eligibility at execution, writes audit records as `system:scheduler`, and safely cancels invalid jobs. Redis remains a connectivity dependency but is not used as the source of scheduling correctness.

The Site still does not implement Integrator retries, replay control APIs, delivery DLQ, media downloading, public feeds, the Texas frontend, or later-phase user/community/AI behavior.
