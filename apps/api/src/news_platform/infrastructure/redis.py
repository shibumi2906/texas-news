from typing import cast

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis:
    return cast(
        Redis,
        Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        ),
    )
