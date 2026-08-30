from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from news_platform.modules.ingestion.application.errors import (
    RateLimitError,
    RateLimitUnavailableError,
)


async def enforce_ingestion_rate_limit(
    redis_client: Any,
    instance_id: UUID,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    if limit <= 0:
        return
    bucket = int(time.time()) // window_seconds
    key = f"ingestion:rate:{instance_id}:{bucket}"
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds + 1)
    except Exception as exc:
        raise RateLimitUnavailableError("ingestion rate limiter unavailable") from exc
    if count > limit:
        raise RateLimitError("ingestion rate limit exceeded")
