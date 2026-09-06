from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from news_platform.api.health import router as health_router
from news_platform.core.config import Settings, get_settings
from news_platform.core.logging import RequestLoggingMiddleware, configure_logging
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.infrastructure.redis import create_redis_client
from news_platform.modules.editorial.api.router import router as editorial_router
from news_platform.modules.engagement.api.router import router as engagement_router
from news_platform.modules.feeds.api.router import router as feeds_router
from news_platform.modules.ingestion.api.router import router as ingestion_router
from news_platform.modules.public_site.api.router import router as public_site_router


def create_app(settings: Settings | None = None) -> FastAPI:
    application_settings = settings or get_settings()
    configure_logging(application_settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_db_engine(application_settings.database_url)
        redis_client = create_redis_client(application_settings.redis_url)
        app.state.settings = application_settings
        app.state.db_engine = engine
        app.state.db_session_factory = create_session_factory(engine)
        app.state.redis = redis_client
        try:
            yield
        finally:
            await redis_client.aclose()
            await engine.dispose()

    application = FastAPI(
        title="Local Entertainment News Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(health_router)
    application.include_router(ingestion_router)
    application.include_router(editorial_router)
    application.include_router(engagement_router)
    application.include_router(feeds_router)
    application.include_router(public_site_router)
    return application


app = create_app()
