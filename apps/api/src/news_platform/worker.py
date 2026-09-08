from __future__ import annotations

import asyncio
import logging
import signal

from sqlalchemy import text

from news_platform.core.config import get_settings
from news_platform.core.logging import configure_logging
from news_platform.infrastructure.database import create_db_engine, create_session_factory
from news_platform.infrastructure.redis import create_redis_client
from news_platform.modules.analytics.application.service import process_analytics_once
from news_platform.modules.editorial.application.service import EditorialService
from news_platform.modules.feeds.infrastructure.cache import invalidate_public_feed_cache

logger = logging.getLogger(__name__)


async def run() -> None:
    """Run scheduled publication and behavioral-event aggregation."""
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    redis_client = create_redis_client(settings.redis_url)
    session_factory = create_session_factory(engine)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stopped.set)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await redis_client.ping()
        logger.info("background_worker_ready")
        while not stopped.is_set():
            if settings.editorial_scheduler_enabled:
                try:
                    async with session_factory() as session, session.begin():
                        published = await EditorialService(session).publish_due(
                            settings.editorial_scheduler_batch_size
                        )
                    if published:
                        await invalidate_public_feed_cache(redis_client)
                        logger.info("scheduled_content_published", extra={"result": published})
                except Exception:
                    logger.exception("editorial_scheduler_iteration_failed")
            if settings.analytics_worker_enabled:
                try:
                    aggregated, invalidated = await process_analytics_once(
                        session_factory,
                        redis_client,
                        settings.analytics_worker_batch_size,
                    )
                    if aggregated.processed or invalidated.delivered:
                        logger.info(
                            "analytics_aggregation_completed",
                            extra={
                                "processed": aggregated.processed,
                                "ranking_updates": aggregated.ranking_updates,
                                "invalidations": invalidated.delivered,
                            },
                        )
                except Exception:
                    logger.exception("analytics_aggregation_iteration_failed")
            enabled_intervals = [
                interval
                for enabled, interval in (
                    (
                        settings.editorial_scheduler_enabled,
                        settings.editorial_scheduler_poll_seconds,
                    ),
                    (
                        settings.analytics_worker_enabled,
                        settings.analytics_worker_poll_seconds,
                    ),
                )
                if enabled
            ]
            poll_seconds = min(enabled_intervals, default=3600)
            try:
                await asyncio.wait_for(stopped.wait(), timeout=poll_seconds)
            except TimeoutError:
                pass
    finally:
        await redis_client.aclose()
        await engine.dispose()
        logger.info("background_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run())
