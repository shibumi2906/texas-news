from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.ai.application.service import (
    AIConfigurationError,
    AIFeatureDisabledError,
    AIResourceNotFoundError,
    AIService,
)
from news_platform.modules.ai.domain.schemas import (
    AIAnswerResponse,
    AIQueryRequest,
    AIQuickBriefRequest,
    StorySummaryResponse,
)
from news_platform.modules.ai.infrastructure.providers import ProviderRegistry
from news_platform.modules.analytics.application.service import AnalyticsIdempotencyConflictError
from news_platform.modules.setup.application.runtime import provider_registry_for_portal
from news_platform.modules.users.application.rate_limit import RateLimitExceededError

router = APIRouter(prefix="/api/v1/portals/{portal_slug}", tags=["ai"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


async def _providers(session: AsyncSession, portal_slug: str, request: Request) -> ProviderRegistry:
    return await provider_registry_for_portal(
        session,
        portal_slug,
        request.app.state.settings,
        request.app.state.ai_providers,
    )


def _error(exc: Exception, status: int, code: str) -> Never:
    raise HTTPException(status, detail={"code": code, "message": str(exc)}) from exc


async def _run(operation: Callable[[], Awaitable[AIAnswerResponse]]) -> AIAnswerResponse:
    try:
        return await operation()
    except AIResourceNotFoundError as exc:
        _error(exc, 404, "AI_RESOURCE_NOT_FOUND")
    except AIFeatureDisabledError as exc:
        _error(exc, 404, "AI_FEATURE_DISABLED")
    except RateLimitExceededError as exc:
        _error(exc, 429, "AI_RATE_LIMIT_EXCEEDED")
    except AnalyticsIdempotencyConflictError as exc:
        _error(exc, 409, "AI_EVENT_ID_CONFLICT")
    except AIConfigurationError as exc:
        _error(exc, 503, "AI_SERVICE_UNAVAILABLE")


@router.get(
    "/stories/{story_slug}/ai-summary",
    response_model=StorySummaryResponse,
)
async def story_summary(
    portal_slug: str,
    story_slug: str,
    request: Request,
    response: Response,
    session: DatabaseSession,
    language: str = Query(min_length=2, max_length=35),
) -> StorySummaryResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with session.begin():
            return await AIService(
                session,
                await _providers(session, portal_slug, request),
                request.app.state.settings,
            ).story_summary(portal_slug, story_slug, language)
    except AIResourceNotFoundError as exc:
        raise HTTPException(404, detail={"code": "AI_RESOURCE_NOT_FOUND"}) from exc
    except AIConfigurationError as exc:
        raise HTTPException(503, detail={"code": "AI_SERVICE_UNAVAILABLE"}) from exc


@router.post("/ai/search", response_model=AIAnswerResponse)
async def ai_search(
    portal_slug: str,
    payload: AIQueryRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AIAnswerResponse:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        service = AIService(
            session, await _providers(session, portal_slug, request), request.app.state.settings
        )
        return await _run(lambda: service.ai_search(portal_slug, payload, request.app.state.redis))


@router.post("/stories/{story_slug}/ai-question", response_model=AIAnswerResponse)
async def story_question(
    portal_slug: str,
    story_slug: str,
    payload: AIQueryRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AIAnswerResponse:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        service = AIService(
            session, await _providers(session, portal_slug, request), request.app.state.settings
        )
        return await _run(
            lambda: service.story_question(
                portal_slug, story_slug, payload, request.app.state.redis
            )
        )


@router.post("/ai/trending", response_model=AIAnswerResponse)
async def trending(
    portal_slug: str,
    payload: AIQuickBriefRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AIAnswerResponse:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        service = AIService(
            session, await _providers(session, portal_slug, request), request.app.state.settings
        )
        return await _run(lambda: service.trending(portal_slug, payload, request.app.state.redis))


@router.post("/ai/today", response_model=AIAnswerResponse)
async def today(
    portal_slug: str,
    payload: AIQuickBriefRequest,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AIAnswerResponse:
    response.headers["Cache-Control"] = "no-store"
    async with session.begin():
        service = AIService(
            session, await _providers(session, portal_slug, request), request.app.state.settings
        )
        return await _run(lambda: service.today(portal_slug, payload, request.app.state.redis))
