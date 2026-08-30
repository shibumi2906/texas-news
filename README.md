# Local Entertainment News Platform

Phase 0 establishes the production-oriented monorepo foundation for the Site Platform. It contains a FastAPI API, a Next.js web shell, PostgreSQL, Redis, an infrastructure-only worker process, migrations, health checks, and code-quality tooling. No content, ingestion, editorial, feed, user, community, or AI functionality is implemented yet.

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
- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT`, `DATABASE_URL`
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

The initial migration is intentionally empty: it establishes a reliable Alembic head while Phase 0 creates no domain tables.

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
