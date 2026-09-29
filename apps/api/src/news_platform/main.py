from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from news_platform.api.health import router as health_router
from news_platform.core.config import Settings, get_settings
from news_platform.core.logging import RequestLoggingMiddleware, configure_logging
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.infrastructure.redis import create_redis_client
from news_platform.modules.advertising.api.router import admin_router as advertising_admin_router
from news_platform.modules.advertising.api.router import router as advertising_router
from news_platform.modules.ai.api.admin_router import router as ai_admin_router
from news_platform.modules.ai.api.router import router as ai_router
from news_platform.modules.ai.infrastructure.providers import ProviderRegistry
from news_platform.modules.analytics.api.router import router as analytics_router
from news_platform.modules.community.api.router import router as community_router
from news_platform.modules.editorial.api.router import router as editorial_router
from news_platform.modules.engagement.api.router import router as engagement_router
from news_platform.modules.feeds.api.router import router as feeds_router
from news_platform.modules.ingestion.api.router import router as ingestion_router
from news_platform.modules.notifications.api.router import (
    admin_router as notifications_admin_router,
)
from news_platform.modules.notifications.api.router import router as notifications_router
from news_platform.modules.public_site.api.router import router as public_site_router
from news_platform.modules.recommendations.api.router import (
    feed_router as recommendation_feed_router,
)
from news_platform.modules.recommendations.api.router import router as recommendations_router
from news_platform.modules.search.api.router import router as search_router
from news_platform.modules.users.api.router import router as users_router


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
        app.state.ai_providers = ProviderRegistry.from_settings(application_settings)
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
    application.include_router(search_router)
    application.include_router(analytics_router)
    application.include_router(users_router)
    application.include_router(community_router)
    application.include_router(recommendations_router)
    application.include_router(recommendation_feed_router)
    application.include_router(ai_router)
    application.include_router(ai_admin_router)
    application.include_router(advertising_router)
    application.include_router(advertising_admin_router)
    application.include_router(notifications_router)
    application.include_router(notifications_admin_router)
    return application


app = create_app()
