from __future__ import annotations

import hashlib
import logging
from typing import Any

from news_platform.modules.feeds.domain.schemas import PublicFeedPage

CACHE_EPOCH_KEY = "public-feeds:epoch"
logger = logging.getLogger(__name__)


class FeedCache:
    def __init__(self, redis_client: Any, ttl_seconds: int) -> None:
        self.redis = redis_client
        self.ttl_seconds = ttl_seconds

    async def epoch(self) -> str:
        try:
            value = await self.redis.get(CACHE_EPOCH_KEY)
            return str(value or "0")
        except Exception:
            logger.warning("feed_cache_epoch_read_failed")
            return "0"

    async def get(self, identity: str, epoch: str) -> PublicFeedPage | None:
        try:
            value = await self.redis.get(self._key(identity, epoch))
        except Exception:
            logger.warning("feed_cache_read_failed")
            return None
        if not value:
            return None
        try:
            return PublicFeedPage.model_validate_json(value)
        except ValueError:
            logger.warning("feed_cache_payload_invalid")
            return None

    async def set(self, identity: str, epoch: str, page: PublicFeedPage) -> None:
        try:
            await self.redis.set(
                self._key(identity, epoch), page.model_dump_json(), ex=self.ttl_seconds
            )
        except Exception:
            logger.warning("feed_cache_write_failed")
            return

    @staticmethod
    def _key(identity: str, epoch: str) -> str:
        digest = hashlib.sha256(identity.encode()).hexdigest()
        return f"public-feeds:{epoch}:{digest}"


async def invalidate_public_feed_cache(redis_client: Any) -> None:
    try:
        await redis_client.incr(CACHE_EPOCH_KEY)
    except Exception:
        logger.warning("feed_cache_invalidation_failed")
        return
