from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from news_platform.api import health


@asynccontextmanager
async def empty_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.db_engine = object()
    app.state.redis = object()
    yield


def build_test_app() -> FastAPI:
    app = FastAPI(lifespan=empty_lifespan)
    app.include_router(health.router)
    return app


def test_liveness_does_not_require_dependencies() -> None:
    with TestClient(build_test_app()) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_success(monkeypatch: object) -> None:
    async def succeeds(_dependency: object) -> None:
        return None

    monkeypatch.setattr(health, "check_database", succeeds)  # type: ignore[attr-defined]
    monkeypatch.setattr(health, "check_redis", succeeds)  # type: ignore[attr-defined]

    with TestClient(build_test_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"postgres": "up", "redis": "up"},
    }


def test_readiness_returns_503_when_a_dependency_is_down(monkeypatch: object) -> None:
    async def succeeds(_dependency: object) -> None:
        return None

    async def fails(_dependency: object) -> None:
        raise ConnectionError("dependency unavailable")

    monkeypatch.setattr(health, "check_database", succeeds)  # type: ignore[attr-defined]
    monkeypatch.setattr(health, "check_redis", fails)  # type: ignore[attr-defined]

    with TestClient(build_test_app()) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"postgres": "up", "redis": "down"},
    }
