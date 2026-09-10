from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.ai.application.service import (
    AIConfigurationError,
    AIResourceNotFoundError,
    AIService,
)
from news_platform.modules.ai.domain.schemas import StorySummaryResponse

router = APIRouter(prefix="/api/v1/portals/{portal_slug}", tags=["ai"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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
                request.app.state.ai_providers,
                request.app.state.settings,
            ).story_summary(portal_slug, story_slug, language)
    except AIResourceNotFoundError as exc:
        raise HTTPException(404, detail={"code": "AI_RESOURCE_NOT_FOUND"}) from exc
    except AIConfigurationError as exc:
        raise HTTPException(503, detail={"code": "AI_SERVICE_UNAVAILABLE"}) from exc
