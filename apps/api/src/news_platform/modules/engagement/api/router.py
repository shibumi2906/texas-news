from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.engagement.application.service import (
    EngagementContentNotFoundError,
    EngagementCounterService,
    EngagementIdempotencyConflictError,
)
from news_platform.modules.engagement.domain.schemas import CounterIncrement, CounterReceipt
from news_platform.modules.feeds.infrastructure.cache import invalidate_public_feed_cache

router = APIRouter(prefix="/internal/v1/engagement", tags=["internal-engagement"])
DatabaseSession = Depends(get_db_session)


@router.post("/counters", response_model=CounterReceipt)
async def increment_counter(
    request: Request,
    payload: CounterIncrement,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    session: AsyncSession = DatabaseSession,
) -> CounterReceipt:
    try:
        async with session.begin():
            receipt = await EngagementCounterService(session).increment(
                content_id=payload.content_id,
                metric=payload.metric,
                amount=payload.amount,
                idempotency_key=idempotency_key,
            )
        if receipt.applied:
            await invalidate_public_feed_cache(request.app.state.redis)
        return receipt
    except EngagementContentNotFoundError as exc:
        raise HTTPException(404, detail={"code": "CONTENT_NOT_FOUND"}) from exc
    except EngagementIdempotencyConflictError as exc:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"}) from exc
    except IntegrityError as exc:
        raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"}) from exc
