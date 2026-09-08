from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response as StarletteResponse

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.analytics.application.service import (
    AnalyticsIdempotencyConflictError,
    AnalyticsIngestionService,
    AnalyticsResourceNotFoundError,
    AnalyticsTimestampError,
)
from news_platform.modules.analytics.domain.schemas import BehaviorEventCreate, BehaviorEventReceipt


class PrivacySafeAnalyticsRoute(APIRoute):
    def get_route_handler(
        self,
    ) -> Callable[[Request], Coroutine[Any, Any, StarletteResponse]]:
        original = super().get_route_handler()

        async def route_handler(request: Request) -> StarletteResponse:
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": {"code": "INVALID_BEHAVIOR_EVENT"}},
                )

        return route_handler


router = APIRouter(
    prefix="/api/v1/portals/{portal_slug}/analytics",
    tags=["public-analytics"],
    route_class=PrivacySafeAnalyticsRoute,
)


@router.post("/events", response_model=BehaviorEventReceipt, status_code=201)
async def collect_event(
    portal_slug: str,
    payload: BehaviorEventCreate,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BehaviorEventReceipt:
    application_settings = request.app.state.settings
    try:
        async with session.begin():
            receipt = await AnalyticsIngestionService(
                session,
                max_age_days=application_settings.analytics_event_max_age_days,
                future_skew_seconds=application_settings.analytics_future_skew_seconds,
            ).collect(portal_slug, payload)
        if receipt.status == "duplicate":
            response.status_code = 200
        response.headers["Cache-Control"] = "no-store"
        return receipt
    except AnalyticsResourceNotFoundError as exc:
        raise HTTPException(
            404, detail={"code": "ANALYTICS_RESOURCE_NOT_FOUND", "message": str(exc)}
        ) from exc
    except AnalyticsTimestampError as exc:
        raise HTTPException(
            422, detail={"code": "INVALID_EVENT_TIMESTAMP", "message": str(exc)}
        ) from exc
    except AnalyticsIdempotencyConflictError as exc:
        raise HTTPException(409, detail={"code": "EVENT_ID_CONFLICT", "message": str(exc)}) from exc
