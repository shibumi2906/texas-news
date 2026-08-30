from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["alive"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["up", "down"]]


async def check_database(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis(redis_client: Redis) -> None:
    await redis_client.ping()


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse(status="alive")


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
async def ready(request: Request) -> ReadyResponse | JSONResponse:
    results = await asyncio.gather(
        check_database(request.app.state.db_engine),
        check_redis(request.app.state.redis),
        return_exceptions=True,
    )
    checks: dict[str, Literal["up", "down"]] = {
        "postgres": "down" if isinstance(results[0], BaseException) else "up",
        "redis": "down" if isinstance(results[1], BaseException) else "up",
    }
    is_ready = all(value == "up" for value in checks.values())
    response = ReadyResponse(status="ready" if is_ready else "not_ready", checks=checks)
    if not is_ready:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )
    return response
