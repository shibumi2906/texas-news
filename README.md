# Local Entertainment News Platform

Phase 1 establishes the production-oriented modular-monolith foundation and initial Site Platform core domain. It contains a FastAPI API, a Next.js web shell, PostgreSQL, Redis, an infrastructure-only worker process, migrations, health checks, core domain models, application services, and code-quality tooling. Integrator ingestion, publication workflows, feeds, users, community, and AI functionality are not implemented yet.

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

The tests create and remove only Phase 1 tables inside `news_platform_test`; they do not touch the development database.

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
