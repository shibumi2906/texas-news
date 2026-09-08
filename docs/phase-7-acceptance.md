# Phase 7 acceptance report

Verified 2026-09-07 against accepted Phase 6 HEAD `897d572`. All Phase 7 changes remain uncommitted.

## Scope and implementation

SPEC section 121 assigns nine behavioral events—impression, click, content open, scroll, video start, watch time, completion, share, and search—and a Trending aggregation pipeline to Phase 7. Section 46 supplies the event fields and requires restraint around sensitive properties. Authentication, users, community, personalization, recommendations, notifications, advertising, AI, full admin UI, and later media UX remain deferred.

The new `analytics` module exposes `POST /api/v1/portals/{portal_slug}/analytics/events`. It validates an active portal, current public content within that portal, optional entity existence, optional geography membership in the portal tree, a timezone-aware timestamp within the configured window, an opaque anonymous or future user identifier, a session identifier, and an event-specific property allowlist. Raw search queries, network identifiers, and arbitrary properties are not stored.

Client-generated event UUIDs are the idempotency identity. An exact replay returns `duplicate`; reuse for different normalized event data returns HTTP 409. PostgreSQL stores immutable raw events separately from aggregation receipts.

The existing worker claims unaggregated events in bounded PostgreSQL batches using `FOR UPDATE SKIP LOCKED`. Impression, click, content-open, watch-time, completion, and share events update the Phase 5 counters through the existing idempotent engagement service. Scroll, video-start, and search events are durably recorded and acknowledged as aggregated without affecting the current Trending formula.

Aggregation receipts and counter changes commit in one PostgreSQL transaction. Ranking changes remain pending for Redis feed-generation invalidation. Redis success marks them delivered; Redis failure rolls back only delivery state, leaving a durable retry. Duplicate work cannot double-count, and an uncertain Redis acknowledgement can only advance the disposable cache generation an extra time.

Migration `0008_phase_7_analytics`, directly after `0007_phase_6_search`, adds `behavior_events`, `behavior_event_aggregations`, validation constraints, foreign keys, and processing indexes. Both a real Phase 6-to-7 upgrade and a clean 0001-to-head chain reached `0008` and passed Alembic check.

## Tests and verification

Forty-two Phase 7 PostgreSQL/Redis cases cover every event type, exact persisted-field fidelity, value-free validation errors, malformed and privacy-unsafe input, finite numeric bounds, counter overflow, timestamp bounds, public content and portal/geography isolation, exact replay, conflicting and concurrent duplicates, aggregation mapping, transactional rollback, no double counting, concurrent delivery/workers, Redis failure/uncertain acknowledgement retry, and Trending cursor invalidation.

| Check | Result |
| --- | --- |
| Full backend pytest | 120 passed; one existing Starlette/httpx deprecation warning |
| Focused Phase 2–7 pytest | 110 passed |
| Focused Phase 7 pytest | 42 passed |
| Ruff check | Passed |
| Ruff format --check | Passed |
| mypy | Passed, 143 source files |
| Alembic Phase 6 → 7 | Passed |
| Alembic clean 0001 → head | Passed |
| Alembic check | Passed, no new operations |
| git diff --check | Passed |
| Frontend lint | Passed |
| Frontend typecheck | Passed |
| Frontend tests | 10 passed |
| Frontend format check | Passed |
| Frontend production build | Passed |

The real Docker development database upgraded to `0008`. A live Texas `content_open` request was accepted, aggregated by the restarted worker, incremented the PostgreSQL view counter, marked its invalidation delivered, and advanced the Redis feed epoch from 2 to 3. PostgreSQL and Redis health checks passed; API and PostgreSQL were healthy, with web and worker running.

No normative contradiction or Phase 7 deviation was found. Phase 8 was not started. The intentionally untracked `docs/github-publish-report.md` was not modified, staged, or included.
