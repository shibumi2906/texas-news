from __future__ import annotations

from typing import Any


class RateLimitExceededError(Exception):
    pass


async def enforce_rate_limit(
    redis_client: Any, key: str, *, limit: int, window_seconds: int
) -> None:
    if limit == 0:
        return
    redis_key = f"phase8:rate:{key}"
    count = await redis_client.incr(redis_key)
    if count == 1:
        await redis_client.expire(redis_key, window_seconds)
    if count > limit:
        raise RateLimitExceededError
