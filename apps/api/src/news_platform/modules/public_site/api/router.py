from typing import Never

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.feeds.application.service import FeedService
from news_platform.modules.feeds.domain.schemas import FeedKind
from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.public_site.domain.schemas import (
    PublicCategoryPage,
    PublicHomepage,
    PublicStory,
)

router = APIRouter(prefix="/api/v1/portals/{portal_slug}", tags=["public-site"])
DatabaseSession = Depends(get_db_session)


def not_found(exc: PublicNotFoundError) -> Never:
    raise HTTPException(
        status_code=404,
        detail={"code": "PUBLIC_RESOURCE_NOT_FOUND", "message": str(exc)},
    ) from exc


@router.get("/home", response_model=PublicHomepage)
async def homepage(
    request: Request, portal_slug: str, session: AsyncSession = DatabaseSession
) -> PublicHomepage:
    try:
        result = await PublicSiteService(session).homepage(portal_slug)
        ranked = await FeedService(
            session,
            request.app.state.redis,
            request.app.state.settings.feed_cache_ttl_seconds,
        ).page(
            portal_slug,
            FeedKind.TRENDING,
            language=result.portal.default_language,
            limit=6,
            cursor_value=None,
        )
        hero_id = result.hero.id if result.hero else None
        result.trending = [item for item in ranked.items if item.id != hero_id][:5]
        return result
    except PublicNotFoundError as exc:
        not_found(exc)


@router.get("/categories/{category_slug}", response_model=PublicCategoryPage)
async def category(
    portal_slug: str,
    category_slug: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = DatabaseSession,
) -> PublicCategoryPage:
    try:
        return await PublicSiteService(session).category(portal_slug, category_slug, offset, limit)
    except PublicNotFoundError as exc:
        not_found(exc)


@router.get("/stories/{story_slug}", response_model=PublicStory)
async def story(
    portal_slug: str,
    story_slug: str,
    session: AsyncSession = DatabaseSession,
) -> PublicStory:
    try:
        return await PublicSiteService(session).story(portal_slug, story_slug)
    except PublicNotFoundError as exc:
        not_found(exc)
