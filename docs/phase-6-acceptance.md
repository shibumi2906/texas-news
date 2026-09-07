# Phase 6 acceptance report

Verified 2026-09-06 against the existing Phase 5 HEAD. All changes remain uncommitted.

## 1. Requirements extracted from SPEC.md

Section 120 assigns PostgreSQL FTS, keyword search, entity search, geography/category/date filtering, and an abstraction for future OpenSearch to Phase 6. Section 11 establishes PostgreSQL as the first search implementation. Existing tenant, publication and frontend/backend domain boundaries apply. The general search roadmap in section 52 does not extend this phase to content-type filters. Sections 121 onward defer behavioral events, users, personalization and AI.

## 2. Plan followed

Read the normative phase and relevant architecture; inspect models, ingestion/editorial boundaries, public read models, feeds/trending/Redis, and frontend conventions; implement isolated search and migration 0007; add the public API and SSR form; add PostgreSQL and frontend tests; run migrations, regression/static/build checks and real-stack/browser verification. No project scaffolding or architecture replacement occurred.

## 3–5. Backend, API and frontend

The new `search` module has domain schemas, an application service and `SearchBackend` protocol, a PostgreSQL adapter, and an API router. It consumes the existing public read-model repository and summary mapper. The endpoint is `GET /api/v1/portals/{portal_slug}/search`. Requests accept required `language` and optional `q`, `entity`, `category`, `geography`, `date_from`, `date_to`, `limit`, `cursor`. Responses expose portal metadata, language, normalized query, public story summaries and `next_cursor`.

The Texas `/search` SSR page has a labeled GET form, search navigation link, existing responsive story cards, preserved filters, next-results link, empty state, validation/unavailable-resource/server-error messages and cursor restart. Fetches use no-store; robots metadata is noindex/follow. No search events are emitted.

## 6. Ranking, indexing and pagination

A stored generated `tsvector` indexes effective title (A), subtitle/description (B) and body (D), with a GIN index. Base language `en` uses English, `es` Spanish, others use `simple`, independently of exact language isolation. Keywords are plain-text AND terms; punctuation and stopwords safely produce no matches. Empty keywords allow filtered browsing. Entity search accepts exact slug or plain words in canonical names and aliases; it is an AND filter, not an entity directory.

Order is `round(ts_rank_cd(...), 6) DESC, site_published_at DESC, id DESC`. Without keywords, all scores are zero. Cursor keyset comparisons use the same expressions. A fixed publication cutoff and transactional PostgreSQL generation bind every page to the same ranking universe. Cursor context includes portal ID, language, normalized keywords, entity/category/geography/date filters. Page size may change. Invalid or stale context returns 400 `INVALID_SEARCH_CURSOR`; traversal must restart.

The generation row is locked FOR SHARE throughout each bounded read transaction. Statement triggers advance it transactionally for content, searchable associations, entities, categories, geography and portals. Writers cannot commit a new generation during a page read. This is deliberately conservative and global: other-portal writes also expire cursors, and search-relevant writers serialize on one row. This is a scaling tradeoff, not a cross-portal disclosure. Search loads at most limit + 1 candidates and hydrates the page in fixed batches, without per-item queries or an unbounded response. The GIN index was confirmed in EXPLAIN with sequential scans disabled on the small integration fixture; this is index eligibility verification, not a production-scale benchmark.

PostgreSQL FTS behavior was cross-checked against the [official PostgreSQL 16 documentation](https://www.postgresql.org/docs/16/textsearch-controls.html).

## 7–8. Visibility and scopes

Centralized public eligibility remains authoritative: editorial `published`, non-null/nonfuture `site_published_at`, upstream neither `retracted` nor `deleted`. Search uses the effective Site fields and returns no ingestion envelopes or history. Slugs, immutable package versions, upstream/editorial separation and portal geography boundaries are unchanged.

The portal must be active; language must be supported and matches `primary_language` exactly. Category must be active/enabled for that portal. A requested geography must be within the portal tree and includes its descendants. Date limits apply to Site publication time, inclusive calendar dates in UTC. All filters combine with AND. No translation or multilingual routing was added.

## 9–10. Database and Redis

New revision: `0007_phase_6_search`, parent `0006_phase_5_feeds`. Adds `content_items.search_vector`, its GIN index, `search_generation`, the generation trigger function, and eight table triggers. Existing rows are indexed on upgrade. Downgrade removes the new objects. Historical migrations are unchanged.

No search caching or Redis changes. Phase 5 cache generations, trending cursors, counter idempotency and invalidation code remain unchanged. PostgreSQL is authoritative for every search page.

## 11. Tests added

20 PostgreSQL tests cover all editorial states, upstream retraction/deletion, null/future publication, portal/language isolation, each effective text field and generated-vector updates, English/Spanish stemming, entity name/alias/slug, category/geography/date intersections, empty/invalid queries, bounded limits, relevance/ties, multi-page traversal, every cursor filter context, cross-portal cursors, stale ranking changes, a concurrent writer blocked by the generation read lock, and GIN index eligibility.

Six frontend tests cover effective results, API request bounds, preserved filters, empty results and API errors 400/404/422/503 with cursor-free restart links. Existing Phase 2–5 tests were not changed.

## 12. Verification results

| Check | Result |
| --- | --- |
| Full backend pytest, real PostgreSQL and Redis | 72 passed |
| Focused Phase 2–6 pytest | 62 passed |
| Focused Phase 6 pytest | 20 passed |
| Ruff check | Passed |
| Ruff format --check | 150 files already formatted |
| mypy | Passed, 135 source files |
| Alembic check on upgraded development DB | Passed, no new operations |
| Alembic check on clean migration DB | Passed, no new operations |
| Frontend lint | Passed |
| Frontend typecheck | Passed |
| Frontend tests in Docker | 10 passed, including 6 new tests |
| Frontend format:check | Passed |
| Frontend production build in Docker | Passed, /search registered as dynamic SSR |
| git diff --check | Passed |

The backend full suite reports one existing Starlette/httpx deprecation warning. Windows host Vitest initially hit sandbox/esbuild filesystem access restrictions; the same suite completed successfully in the existing Docker web service. An intermediate frontend error-mocking test failed; switching to the actual HTTP client with mocked fetch verified the real error path, and all final tests passed.

## 13. Real Docker verification

All five services remain running: API/PostgreSQL/Redis healthy, web and worker up. PostgreSQL `pg_isready` succeeded and Redis returned PONG. The existing local development database upgraded from 0006 to 0007 successfully. A separate new database `news_phase6_migration_test` completed the full empty -> 0001 -> 0007 chain and Alembic check. It remains available for inspection; no development database or volume was deleted.

The real public API returned the existing published Dallas Arts District story for keyword Texas. The real web route `/search?q=Texas` returned HTTP 200 and rendered that result. The browser showed the search form/results and submitted a new query, yielding the expected empty state. The expired-cursor page returned HTTP 200 with its restart UI; the backend rejects the cursor with HTTP 400. Browser and HTTP verification use the real web/API/PostgreSQL stack. No mock stories were inserted into the development database.

## 14–15. Deviations and deferrals

No deviations from the explicit Phase 6 requirements. Parameters, UTC date semantics, weights, plain-word matching and global generation are documented implementation choices where SPEC leaves details open. No normative contradiction was found. SPEC.md, NEWS_INTEGRATOR_INTERFACE.md and the visual reference remain unchanged.

Deferred: Phase 7 behavioral events/aggregation, authentication/users/community, personalization/recommendations, notifications/advertising, Site AI/AI search, OpenSearch deployment, translation/language switching, full admin frontend, extra media processing. Content-type search filters, suggestions and highlighting are outside explicit Phase 6 scope and were not added.

## 16. Files added/changed

- Changed: `README.md`
- Changed: `apps/api/src/news_platform/main.py`
- Changed: `apps/api/src/news_platform/modules/content/domain/models.py`
- Changed: `apps/api/src/news_platform/modules/models.py`
- Changed: `apps/web/src/app/styles.css`
- Changed: `apps/web/src/components/public-site.tsx`
- Changed: `apps/web/src/lib/public-api.ts`
- Added: `apps/api/alembic/versions/0007_phase_6_search.py`
- Added: `apps/api/src/news_platform/modules/search/__init__.py`
- Added: `apps/api/src/news_platform/modules/search/api/__init__.py`
- Added: `apps/api/src/news_platform/modules/search/api/router.py`
- Added: `apps/api/src/news_platform/modules/search/application/__init__.py`
- Added: `apps/api/src/news_platform/modules/search/application/port.py`
- Added: `apps/api/src/news_platform/modules/search/application/service.py`
- Added: `apps/api/src/news_platform/modules/search/domain/__init__.py`
- Added: `apps/api/src/news_platform/modules/search/domain/models.py`
- Added: `apps/api/src/news_platform/modules/search/domain/schemas.py`
- Added: `apps/api/src/news_platform/modules/search/infrastructure/__init__.py`
- Added: `apps/api/src/news_platform/modules/search/infrastructure/postgres.py`
- Added: `apps/api/tests/test_phase_6_search.py`
- Added: `apps/web/src/app/search/page.test.tsx`
- Added: `apps/web/src/app/search/page.tsx`
- Added: `apps/web/src/components/search-view.tsx`
- Added: `docs/phase-6-acceptance.md`

## 17. git diff --stat

Tracked-file diff (Git does not include untracked additions here; all additions are listed above):

```text
 README.md                                          | 25 ++++++++++++++++++-
 apps/api/src/news_platform/main.py                 |  2 ++
 .../news_platform/modules/content/domain/models.py | 25 ++++++++++++++++++-
 apps/api/src/news_platform/modules/models.py       |  2 ++
 apps/web/src/app/styles.css                        | 28 ++++++++++++++++++++++
 apps/web/src/components/public-site.tsx            |  1 +
 apps/web/src/lib/public-api.ts                     | 11 +++++++++
 7 files changed, 92 insertions(+), 2 deletions(-)
```

## 18. git status --short

```text
 M README.md
 M apps/api/src/news_platform/main.py
 M apps/api/src/news_platform/modules/content/domain/models.py
 M apps/api/src/news_platform/modules/models.py
 M apps/web/src/app/styles.css
 M apps/web/src/components/public-site.tsx
 M apps/web/src/lib/public-api.ts
?? apps/api/alembic/versions/0007_phase_6_search.py
?? apps/api/src/news_platform/modules/search/
?? apps/api/tests/test_phase_6_search.py
?? apps/web/src/app/search/
?? apps/web/src/components/search-view.tsx
?? docs/phase-6-acceptance.md
```

## 19. Acceptance

Phase 6 is ready for acceptance. All requested final checks passed. Changes remain uncommitted; Phase 7 was not started.
