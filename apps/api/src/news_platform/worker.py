from __future__ import annotations

import asyncio
import logging
import signal

from sqlalchemy import text

from news_platform.core.config import get_settings
from news_platform.core.logging import configure_logging
from news_platform.infrastructure.database import create_db_engine
from news_platform.infrastructure.redis import create_redis_client

logger = logging.getLogger(__name__)


async def run() -> None:
    """Run the Phase 0 worker container without registering future domain jobs."""
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_db_engine(settings.database_url)
    redis_client = create_redis_client(settings.redis_url)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stopped.set)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await redis_client.ping()
        logger.info("worker_skeleton_ready")
        await stopped.wait()
    finally:
        await redis_client.aclose()
        await engine.dispose()
        logger.info("worker_skeleton_stopped")


if __name__ == "__main__":
    asyncio.run(run())
