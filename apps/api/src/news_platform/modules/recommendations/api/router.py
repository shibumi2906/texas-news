from typing import Annotated, Never

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.feeds.domain.schemas import FeedKind, PublicFeedPage
from news_platform.modules.recommendations.application.service import (
    RecommendationFeedService,
    RecommendationsDisabledError,
    RecommendationTargetNotFoundError,
    UserInterestService,
)
from news_platform.modules.recommendations.domain.cursor import InvalidRecommendationCursorError
from news_platform.modules.recommendations.domain.schemas import (
    InterestCatalog,
    UserInterestsUpdate,
    UserInterestsView,
)
from news_platform.modules.users.api.dependencies import csrf_protected_user, current_user
from news_platform.modules.users.application.service import AuthenticatedUser

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/recommendations", tags=["recommendations"])
feed_router = APIRouter(prefix="/api/v1/portals/{portal_slug}/feeds", tags=["personalized-feeds"])
ReadUser = Annotated[AuthenticatedUser, Depends(current_user)]
ProtectedUser = Annotated[AuthenticatedUser, Depends(csrf_protected_user)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _error(exc: Exception, status: int, code: str) -> Never:
    raise HTTPException(status, detail={"code": code, "message": str(exc)}) from exc


@router.get("/me/interests", response_model=UserInterestsView)
async def interests(auth: ReadUser, session: DatabaseSession) -> UserInterestsView:
    try:
        return await UserInterestService(session).get(auth)
    except RecommendationsDisabledError as exc:
        _error(exc, 404, "RECOMMENDATIONS_DISABLED")


@router.get("/me/interest-catalog", response_model=InterestCatalog)
async def interest_catalog(auth: ReadUser, session: DatabaseSession) -> InterestCatalog:
    try:
        return await UserInterestService(session).catalog(auth)
    except RecommendationsDisabledError as exc:
        _error(exc, 404, "RECOMMENDATIONS_DISABLED")


@router.put("/me/interests", response_model=UserInterestsView)
async def replace_interests(
    payload: UserInterestsUpdate, auth: ProtectedUser, session: DatabaseSession
) -> UserInterestsView:
    try:
        result = await UserInterestService(session).replace(auth, payload)
        await session.commit()
        return result
    except RecommendationTargetNotFoundError as exc:
        _error(exc, 404, "INTEREST_TARGET_NOT_FOUND")
    except RecommendationsDisabledError as exc:
        _error(exc, 404, "RECOMMENDATIONS_DISABLED")
    except ValueError as exc:
        await session.rollback()
        _error(exc, 422, "INVALID_INTERESTS")


async def _page(
    auth: AuthenticatedUser,
    session: AsyncSession,
    feed: FeedKind,
    language: str,
    limit: int,
    cursor: str | None,
) -> PublicFeedPage:
    try:
        return await RecommendationFeedService(session).page(
            auth, feed, language=language, limit=limit, cursor_value=cursor
        )
    except InvalidRecommendationCursorError as exc:
        _error(exc, 400, "INVALID_RECOMMENDATION_CURSOR")
    except RecommendationTargetNotFoundError as exc:
        _error(exc, 404, "RECOMMENDATION_RESOURCE_NOT_FOUND")
    except RecommendationsDisabledError as exc:
        _error(exc, 404, "RECOMMENDATIONS_DISABLED")
    except ValueError as exc:
        _error(exc, 400, "INVALID_RECOMMENDATION_CURSOR")


@feed_router.get("/for-you", response_model=PublicFeedPage)
async def for_you(
    auth: ReadUser,
    session: DatabaseSession,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1200),
) -> PublicFeedPage:
    return await _page(auth, session, FeedKind.FOR_YOU, language, limit, cursor)


@feed_router.get("/following", response_model=PublicFeedPage)
async def following(
    auth: ReadUser,
    session: DatabaseSession,
    language: str = Query(min_length=2, max_length=35),
    limit: int = Query(ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=1200),
) -> PublicFeedPage:
    return await _page(auth, session, FeedKind.FOLLOWING, language, limit, cursor)
