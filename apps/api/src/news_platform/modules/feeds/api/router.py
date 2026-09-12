from typing import Never

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.feeds.application.service import FeedService
from news_platform.modules.feeds.domain.cursor import InvalidFeedCursorError
from news_platform.modules.feeds.domain.schemas import FeedKind, PublicFeedPage
from news_platform.modules.public_site.application.service import PublicNotFoundError

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/feeds", tags=["public-feeds"])
DatabaseSession = Depends(get_db_session)


def feed_error(exc: Exception, status_code: int, code: str) -> Never:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc


async def feed_page(
    request: Request,
    session: AsyncSession,
    portal_slug: str,
    feed: FeedKind,
    language: str,
    limit: int,
    cursor: str | None,
    scope: str | None = None,
) -> PublicFeedPage:
    try:
        return await FeedService(
            session,
            request.app.state.redis,
            request.app.state.settings.feed_cache_ttl_seconds,
        ).page(
            portal_slug,
            feed,
            language=language,
            limit=limit,
            cursor_value=cursor,
            scope=scope,
        )
    except PublicNotFoundError as exc:
        feed_error(exc, 404, "PUBLIC_RESOURCE_NOT_FOUND")
    except InvalidFeedCursorError as exc:
        feed_error(exc, 400, "INVALID_FEED_CURSOR")


@router.get("/home", response_model=PublicFeedPage)
async def home(
    request: Request,
    portal_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(request, session, portal_slug, FeedKind.HOME, language, limit, cursor)


@router.get("/latest", response_model=PublicFeedPage)
async def latest(
    request: Request,
    portal_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(request, session, portal_slug, FeedKind.LATEST, language, limit, cursor)


@router.get("/trending", response_model=PublicFeedPage)
async def trending(
    request: Request,
    portal_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(
        request, session, portal_slug, FeedKind.TRENDING, language, limit, cursor
    )


@router.get("/shorts", response_model=PublicFeedPage)
async def shorts(
    request: Request,
    portal_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(request, session, portal_slug, FeedKind.SHORTS, language, limit, cursor)


@router.get("/categories/{category_slug}", response_model=PublicFeedPage)
async def category(
    request: Request,
    portal_slug: str,
    category_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(
        request,
        session,
        portal_slug,
        FeedKind.CATEGORY,
        language,
        limit,
        cursor,
        category_slug,
    )


@router.get("/local/{geography_slug}", response_model=PublicFeedPage)
async def local(
    request: Request,
    portal_slug: str,
    geography_slug: str,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1000),
    session: AsyncSession = DatabaseSession,
) -> PublicFeedPage:
    return await feed_page(
        request,
        session,
        portal_slug,
        FeedKind.LOCAL,
        language,
        limit,
        cursor,
        geography_slug,
    )
