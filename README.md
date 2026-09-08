# Local Entertainment News Platform

Phase 8 adds portal-scoped accounts, profiles, sessions, comments, replies, reactions, reports, saves, follows, and moderation status. It preserves the Phase 0–7 ingestion, editorial, public visibility, feeds, search, analytics, and Redis consistency boundaries. Personalization, recommendations, notifications, and Site AI remain deferred.

## Prerequisites

- Docker Desktop with Docker Compose v2 (recommended path)
- For host development: Python 3.12+ and Node.js 22+

## Initial setup

From the repository root:

```powershell
Copy-Item .env.example .env
```

The example values are local-development defaults only. Change credentials before using a shared or production-like environment. Never commit `.env`.

## Start and stop the complete stack

Build and start `web`, `api`, `worker`, `postgres`, and `redis`:

```powershell
docker compose up --build
```

Run in the background:

```powershell
docker compose up --build --detach
```

Open the web shell at <http://localhost:3000>. The API documentation is at <http://localhost:8000/docs>.

Stop containers:

```powershell
docker compose down
```

To also remove local database and Redis volumes (destructive to local container data):

```powershell
docker compose down --volumes
```

## Environment variables

All supported Phase 0 variables are documented in `.env.example`:

- `ENVIRONMENT`, `LOG_LEVEL`
- `API_HOST`, `API_PORT`
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `DATABASE_URL`, `POSTGRES_TEST_URL`
- `REDIS_PORT`, `REDIS_URL`
- `INGESTION_CLOCK_SKEW_SECONDS`, `INGESTION_RATE_LIMIT`, `INGESTION_RATE_LIMIT_WINDOW_SECONDS`
- `EDITORIAL_SCHEDULER_ENABLED`, `EDITORIAL_SCHEDULER_POLL_SECONDS`, `EDITORIAL_SCHEDULER_BATCH_SIZE`
- `FEED_CACHE_TTL_SECONDS`
- `ANALYTICS_EVENT_MAX_AGE_DAYS`, `ANALYTICS_FUTURE_SKEW_SECONDS`
- `ANALYTICS_WORKER_ENABLED`, `ANALYTICS_WORKER_POLL_SECONDS`, `ANALYTICS_WORKER_BATCH_SIZE`
- `WEB_PORT`, `API_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`

Compose supplies container-network database and Redis URLs to backend services. Host commands use `DATABASE_URL` and `REDIS_URL` from `.env`.

## Backend host development

```powershell
Set-Location apps/api
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
./.venv/Scripts/python.exe -m uvicorn news_platform.main:app --reload
```

Backend tests and checks:

```powershell
Set-Location apps/api
./.venv/Scripts/python.exe -m pytest
./.venv/Scripts/python.exe -m ruff check .
./.venv/Scripts/python.exe -m ruff format --check .
./.venv/Scripts/python.exe -m mypy
```

Apply migrations against the host-configured database:

```powershell
Set-Location apps/api
./.venv/Scripts/python.exe -m alembic upgrade head
```

Apply migrations through Compose:

```powershell
docker compose run --rm api alembic upgrade head
```

The Phase 0 migration is an empty baseline. Phase 1 adds the core domain schema after that baseline.

Phase 2 adds Integrator connection keys, immutable incoming packages and versions, and the source-package link on `ContentVersion`.

Phase 3 adds independent upstream/editorial state, scheduling fields, version origin, and the editorial audit log.

Phase 4 adds stable public story slugs. Existing rows receive deterministic UUID-based slugs during migration; newly ingested stories receive a readable title slug with a package-identity suffix.

Phase 5 adds PostgreSQL aggregate engagement counters and idempotency receipts. Redis remains a disposable read cache rather than an authoritative lifecycle or counter store.

## Phase 1 core domain

The backend modules under `apps/api/src/news_platform/modules` define:

- portals;
- hierarchical geography;
- categories and topics;
- named entities;
- sources, content items, and immutable content versions;
- media assets;
- content-to-category, topic, entity, and geography associations.

No public content API or Integrator receiver is exposed in Phase 1. Application services are tested directly.

### Texas seed

Apply migrations, then run the idempotent seed through Compose:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api python -m news_platform.seed
```

The seed creates `World → United States → Texas`, the Texas portal, and the eleven initial categories. Re-running it does not create duplicates.

### PostgreSQL integration tests

Phase 1 integration tests require a dedicated real PostgreSQL database. Create it once using the local Compose PostgreSQL service:

```powershell
docker compose exec postgres createdb -U news_platform news_platform_test
```

Then run the full backend suite from `apps/api`:

```powershell
$env:POSTGRES_TEST_URL="postgresql+asyncpg://news_platform:news_platform_dev@localhost:5432/news_platform_test"
./.venv/Scripts/python.exe -m pytest
```

The tests create and remove only Site Platform tables inside `news_platform_test`; they do not touch the development database.

## Phase 2 Integrator receiver

The internal receiver is:

```text
POST /internal/v1/ingestion/content
```

It accepts exactly canonical schema `1.0` and `1.1`. Wire payload fields follow `NEWS_INTEGRATOR_INTERFACE.md` and the generated Integrator `CanonicalNewsPackageEnvelope` schema. Required request headers are:

```text
Idempotency-Key: <package_id>:<package_version>
X-Integrator-Instance-Id: <instance UUID>
X-Signing-Key-Id: <key identifier>
X-Timestamp: <timezone-aware ISO-8601 timestamp>
X-Signature: <hex HMAC-SHA256>
```

The HMAC message is the UTF-8 timestamp bytes immediately followed by the exact HTTP request body bytes. The receiver never parses and reserializes the body before signature verification. The default clock-skew allowance is 300 seconds.

Provision a development connection after applying migrations. Supply the secret through the process environment so it is not passed on the command line:

```powershell
$env:INTEGRATOR_HMAC_SECRET="replace-with-a-development-secret"
docker compose exec -e INTEGRATOR_HMAC_SECRET api python -m news_platform.modules.ingestion.infrastructure.provision --instance-id 11111111-1111-4111-8111-111111111111 --name "Development Integrator" --key-id dev-active
Remove-Item Env:INTEGRATOR_HMAC_SECRET
```

The Phase 2 database stores active and optional previous secrets in PostgreSQL because encryption-at-rest/key-vault infrastructure does not yet exist. Access to that database must be restricted and production deployments must provide storage-level encryption or a secrets adapter before using production credentials. Secrets are never returned or logged.

Successful new versions return HTTP 201 and `status: accepted`; exact duplicates return HTTP 200 and `status: duplicate`. Conflicting bytes for an existing package/version return HTTP 409. Authentication failures return HTTP 401, unsupported/invalid packages return HTTP 422, and rate limiting returns HTTP 429.

Current mapping rules:

- canonical content and primary source provenance map into `ContentItem` and `Source`;
- every accepted source package gets a distinct `ContentVersion`, whose independent Site `version_number` is allocated separately from `source_revision`;
- typed categories, topics, structured geographies, reliably typed entities, and media map into Phase 1 models;
- typed schema 1.1 taxonomy takes precedence; legacy `taxonomy` maps to topics only when typed taxonomy is absent;
- legacy `regions`, language versions, AI provenance, rights, warnings, and the full validated package remain preserved losslessly in JSONB for later phases;
- media remains remote metadata only and `rights_hint` does not imply permission to copy it.

After an editorial edit, later upstream versions remain stored and update source provenance and associations, but do not overwrite the current editorial title, subtitle, description, or body. The Integrator `content.lead` maps to Site `subtitle`; both source and editorial versions retain that value in version metadata. The explicit `has_editorial_override` marker preserves this deterministic Phase 3 policy for future conflict handling.

Run all PostgreSQL receiver tests:

```powershell
Set-Location apps/api
$env:POSTGRES_TEST_URL="postgresql+asyncpg://news_platform:news_platform_dev@localhost:5432/news_platform_test"
./.venv/Scripts/python.exe -m pytest -q
```

## Phase 3 editorial publication

The internal API is rooted at `/api/v1/admin/content`. It supports list and detail reads, `ready`, `publish`, `unpublish`, `schedule`, `cancel-schedule`, `restore`, and an explicit-field `PATCH` for title, subtitle, description, and body. Every request requires an `X-Editorial-Actor` header. This actor identifier exists only for audit attribution; it is not authentication or authorization, which remains deferred to Phase 8.

The implemented transitions are explicit: `received|processing -> ready`, `ready -> scheduled|published`, `scheduled -> ready|published`, `published -> unpublished|retracted`, `unpublished -> scheduled|published|archived`, `archived -> ready|unpublished`, and `retracted -> ready`. Deleted content has no outbound transition. Active upstream `retracted` or `deleted` state blocks publish, schedule, and restore regardless of editorial state.

Restore publishes an editorially unpublished item when its upstream state allows publication. Archived or retracted editorial state restores to `ready`; an active upstream retraction/deletion always wins. Repeating publish for an already published item is idempotent and does not create another audit event or version.

Run the scheduler locally as part of Compose:

```powershell
docker compose up --build --detach worker
docker compose logs --follow worker
```

Example workflow (replace the content UUID):

```powershell
$headers = @{ "X-Editorial-Actor" = "editor:local" }
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" -Body "{}" http://localhost:8000/api/v1/admin/content/<id>/ready
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" -Body '{"reason":"approved"}' http://localhost:8000/api/v1/admin/content/<id>/publish
Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" -Body '{"reason":"hold"}' http://localhost:8000/api/v1/admin/content/<id>/unpublish
```

Schedule requests use a timezone-aware future `scheduled_at`; the worker polls PostgreSQL, locks due rows with `FOR UPDATE SKIP LOCKED`, rechecks eligibility, and records publication as actor `system:scheduler`. PostgreSQL locking is authoritative, so repeated or concurrent worker execution cannot create duplicate publication events.

## Frontend host development

```powershell
Set-Location apps/web
npm ci
npm run dev
```

Frontend tests and checks:

```powershell
Set-Location apps/web
npm run lint
npm run typecheck
npm run test:run
npm run format:check
npm run build
```

## Phase 4 Texas public portal

The public backend is rooted at `/api/v1/portals/{portal_slug}`:

```text
GET /api/v1/portals/texas/home
GET /api/v1/portals/texas/categories/{category_slug}?offset=0&limit=20
GET /api/v1/portals/texas/stories/{story_slug}
```

All three surfaces use one backend publication policy. A story is public only when its editorial status is `published`, its `site_published_at` is present and not in the future, and its current upstream status is neither `retracted` nor `deleted`. Portal scope is validated by the active portal and its primary geography tree, so Texas includes associated Texas cities and metros without leaking another portal's geography. Ordering is `site_published_at DESC, id ASC` for a stable tie-break.

The homepage supplies the Hero, calculated Trending stories, configured category sections, and published video highlights. The original category API remains available for Phase 4 compatibility; Phase 5 listing pages use cursor feeds.

Next.js reads the API server-side using `API_BASE_URL`. Open <http://localhost:3000> for the Texas homepage, `/<category-slug>` for category pages, and `/story/<story-slug>` for story pages. Canonical URLs originate in backend portal configuration (`seo_settings.canonical_base_url` when set, otherwise the portal domain), and the frontend renders page metadata, Open Graph data, and NewsArticle JSON-LD from the public response.

## Phase 5 feeds and trending

All feed requests require `language` and `limit`; `cursor` is omitted for the first page and returned as an opaque `next_cursor` when more content exists:

```text
GET /api/v1/portals/{portal_slug}/feeds/home
GET /api/v1/portals/{portal_slug}/feeds/latest
GET /api/v1/portals/{portal_slug}/feeds/trending
GET /api/v1/portals/{portal_slug}/feeds/categories/{category_slug}
GET /api/v1/portals/{portal_slug}/feeds/local/{geography_slug}
```

Chronological feeds order by `site_published_at DESC, id DESC`. Trending combines aggregate engagement, CTR, view velocity, freshness decay, local relevance, and content quality, then uses publication time and content ID as stable tie-breakers. Weights are read from `Portal.ranking_settings.trending`, with deterministic defaults when no override exists.

The internal aggregate-counter boundary is `POST /internal/v1/engagement/counters`. It requires an `Idempotency-Key` header and atomically applies a positive metric delta in PostgreSQL. It intentionally does not collect user/session behavioral events; that event pipeline belongs to Phase 7.

Feed responses are cached in Redis for `FEED_CACHE_TTL_SECONDS`. Cache keys include a generation epoch, portal, feed, scope, language, page size, and cursor. Successful ingestion, editorial mutations, scheduled publication, and applied counter changes advance the epoch after the PostgreSQL transaction commits, so old cached generations cannot re-expose retracted, deleted, or unpublished content.

The Texas frontend exposes `/latest`, `/trending`, `/local/texas`, cursor-backed category pages, and the existing homepage/story pages.

## Health verification

Liveness confirms only that the API process is running:

```powershell
Invoke-RestMethod http://localhost:8000/health/live
```

Readiness checks both PostgreSQL and Redis and returns HTTP 503 if either is unavailable:

```powershell
Invoke-RestMethod http://localhost:8000/health/ready
```

Container dependency status:

```powershell
docker compose ps
docker compose exec postgres pg_isready -U news_platform -d news_platform
docker compose exec redis redis-cli ping
```

## One-command checks

After installing host dependencies, run all static and test checks plus Compose validation:

```powershell
./scripts/verify.ps1
```

## Repository layout

```text
apps/
  api/          FastAPI application, worker skeleton, Alembic, backend tests
  web/          Next.js App Router application and component test
packages/
  shared/       Reserved shared-contract boundary
infra/          Infrastructure documentation and future deployment assets
docs/           Architecture documentation
scripts/        Developer automation
references/     Visual references for later frontend phases
```

The Texas homepage reference is preserved for Phase 4. It is not implemented or copied in Phase 0.

## Phase 6 search

Open `/search` on the Texas frontend. The GET form supports keywords, entity name/alias/slug, location slug, enabled category, and inclusive UTC publication dates. It preserves filters when following the next-results link and provides a restart action for expired cursors. Search pages are dynamic, use no-store API fetches, and are marked noindex.

```text
GET /api/v1/portals/texas/search?language=en&q=mavericks&limit=20
GET /api/v1/portals/texas/search?language=en&entity=dallas-mavericks&geography=dallas&category=sports&date_from=2026-09-01&date_to=2026-09-06
```

`language` is required and must be enabled for the active portal. Optional fields are `q` (max 200 characters), `entity`, `category`, `geography` (max 180 each), `date_from`, `date_to` (ISO dates), `limit` (1–50, default 20), and `cursor`. Empty keywords browse matching public stories; punctuation-only or stopword-only keywords return no matches. Queries use plain words with AND semantics, without exposing SQL or tsquery syntax. All filters combine with AND. Entity matches use exact slug or words in the canonical name/aliases. Geography includes descendants and must belong to the portal tree. Date boundaries apply to `site_published_at` in UTC; both dates are inclusive.

Migration `0007_phase_6_search` adds a stored generated `tsvector` and GIN index on effective title (A), subtitle/description (B), and body (D). The language base `en` selects English, `es` Spanish, and other supported languages use PostgreSQL `simple`; exact content-language isolation still applies. No translation or language switching is introduced. Generated vectors update transactionally on editorial and source changes without reading ingestion envelopes or version history.

Results order by `ts_rank_cd` rounded to six decimals DESC, `site_published_at DESC`, then content UUID DESC. With no keyword, rank is zero. Hydration reuses the public read model in bounded batches, with at most `limit + 1` candidate rows and no per-story queries. Responses contain public story summaries, never vectors or ingestion payloads. The `SearchBackend` protocol isolates the adapter and can be implemented by a future OpenSearch backend.

An opaque versioned cursor binds to portal ID, normalized query, language, every filter, a fixed publication cutoff, rank, publication timestamp, content ID, and PostgreSQL search generation. Changing page size is allowed. A cursor from another context or generation returns HTTP 400 `INVALID_SEARCH_CURSOR`; clients must restart. Invalid fields return 422; unknown portal, unsupported language, disabled/unknown category, or out-of-portal geography returns 404.

The migration also adds a singleton `search_generation` row and statement triggers on content, its searchable associations, entities, categories, geography nodes, and portals. Changes advance the generation in the same PostgreSQL transaction. Search holds a shared generation-row lock until its bounded read transaction completes, so a concurrent writer cannot commit a new ranking universe during a page read. This generation is deliberately global: even another portal's search-relevant write can require restarting traversal. This favors consistency at current scale; the row serializes search-relevant writers and may warrant partitioning at higher write volume. Rollbacks do not invalidate cursors. Redis is not involved in search; the Phase 5 cache/cursor implementation is unchanged.

Search reuses centralized public eligibility: published editorial state, nonfuture `site_published_at`, and no upstream retraction/deletion. Every page is re-read from PostgreSQL. New publications after the cursor cutoff are excluded; changes to existing publication eligibility invalidate traversal.

FTS and pagination integration tests are in `apps/api/tests/test_phase_6_search.py`; frontend tests are in `apps/web/src/app/search/page.test.tsx`. See `docs/phase-6-acceptance.md` for acceptance verification.

## Phase 7 analytics and behavioral events

The public collection boundary is:

```text
POST /api/v1/portals/{portal_slug}/analytics/events
```

It accepts `impression`, `click`, `content_open`, `scroll`, `video_start`, `watch_time`, `completion`, `share`, and `search`. Each event carries a client-generated UUID, anonymous/session identifiers, timezone-aware timestamp, optional content/entity/geography references, and a small event-specific properties object. Raw queries, user IDs, and arbitrary properties are rejected so the analytics store cannot impersonate an account or become an accidental personal-data sink.

Content events require content that is currently public inside the active portal. Geography references must be inside that portal's hierarchy. Timestamps may be at most seven days old or five minutes in the future by default. Exact UUID replay returns `duplicate`; reusing a UUID for different data returns `EVENT_ID_CONFLICT`.

Raw `behavior_events` are immutable. The existing worker claims unaggregated rows with `FOR UPDATE SKIP LOCKED`, writes separate aggregation receipts, and maps impressions, clicks, content opens, watch time, completions, and shares through the Phase 5 idempotent engagement service. Scroll, video start, and search remain durable analytics without changing current Trending inputs.

Ranking updates create a transactional PostgreSQL invalidation outbox. The worker advances the Redis feed generation and then marks those receipts delivered. Redis failure leaves the outbox pending for retry; replay cannot double-count PostgreSQL counters, and an uncertain Redis delivery can only produce an extra harmless generation advance. Redis remains a cache, not the event or aggregate authority.

## Phase 8 users and community

Email registration and login use provider identities so Google, Apple, or another provider can be linked later without changing the user model. Passwords use salted `scrypt`; opaque session tokens are stored only as SHA-256 digests. The API sets host-only HttpOnly session cookies and a session-bound CSRF cookie, enforces an origin allowlist plus `X-CSRF-Token` on mutations, expires/revokes sessions, and applies Redis login/comment/reaction rate limits. Roles are `user`, `moderator`, `editor`, `admin`, and `system`; only moderator/admin sessions can change comment status.

Public community routes live under `/api/v1/portals/{portal_slug}/community`. Anonymous readers can list visible comments. Authenticated users can create idempotent UUID-keyed comments/replies, edit or soft-remove only their own comments, select one reaction per story or comment, report a visible comment once, toggle saves, and follow public story entities/topics or in-portal geography. The story page exposes registration/login, profile editing, comments, reply/like/reaction/report, save, and entity-follow controls through a same-origin Next.js rewrite.

Every content interaction reuses the centralized public eligibility policy and session portal; hidden, unpublished, retracted, deleted, cross-portal, or disabled-community resources are not reachable. PostgreSQL is authoritative. Unique constraints plus transaction-scoped advisory locks make retries and concurrent toggles deterministic, while engagement counts change in the same transaction as their source records. Moderation changes are audited. New authenticated community behavior events use only the authenticated server identity and never alter or link historical anonymous events.
