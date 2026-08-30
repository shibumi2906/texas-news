$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot/../apps/api"
try {
    ./.venv/Scripts/python.exe -m pytest
    ./.venv/Scripts/python.exe -m ruff check .
    ./.venv/Scripts/python.exe -m ruff format --check .
    ./.venv/Scripts/python.exe -m mypy
} finally {
    Pop-Location
}

Push-Location "$PSScriptRoot/../apps/web"
try {
    npm run lint
    npm run typecheck
    npm run test:run
    npm run format:check
    npm run build
} finally {
    Pop-Location
}

docker compose config --quiet
