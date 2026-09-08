from __future__ import annotations

from collections.abc import Awaitable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.community.application.service import (
    CommunityConflictError,
    CommunityDisabledError,
    CommunityForbiddenError,
    CommunityNotFoundError,
    CommunityService,
    InvalidCursorError,
)
from news_platform.modules.community.domain.models import FollowTargetType
from news_platform.modules.community.domain.schemas import (
    CommentCreate,
    CommentPage,
    CommentUpdate,
    CommentView,
    FollowView,
    ModerationUpdate,
    ReactionUpdate,
    ReportCreate,
    ReportView,
    SaveView,
    ToggleView,
)
from news_platform.modules.users.api.dependencies import (
    csrf_protected_user,
    current_user,
    require_moderator,
)
from news_platform.modules.users.application.rate_limit import (
    RateLimitExceededError,
    enforce_rate_limit,
)
from news_platform.modules.users.application.service import AuthenticatedUser

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/community", tags=["community"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
ProtectedUser = Annotated[AuthenticatedUser, Depends(csrf_protected_user)]
ReadUser = Annotated[AuthenticatedUser, Depends(current_user)]


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, CommunityNotFoundError):
        return HTTPException(404, detail={"code": "COMMUNITY_RESOURCE_NOT_FOUND"})
    if isinstance(exc, CommunityDisabledError):
        return HTTPException(404, detail={"code": "COMMUNITY_DISABLED"})
    if isinstance(exc, CommunityForbiddenError):
        return HTTPException(403, detail={"code": "FORBIDDEN"})
    if isinstance(exc, InvalidCursorError):
        return HTTPException(400, detail={"code": "INVALID_COMMENT_CURSOR"})
    return HTTPException(409, detail={"code": "COMMUNITY_CONFLICT"})


async def _commit[T](session: AsyncSession, operation: Awaitable[T]) -> T:
    try:
        result = await operation
        await session.commit()
        return result
    except (
        CommunityNotFoundError,
        CommunityDisabledError,
        CommunityForbiddenError,
        CommunityConflictError,
        InvalidCursorError,
    ) as exc:
        await session.rollback()
        raise _error(exc) from exc
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, detail={"code": "COMMUNITY_CONFLICT"}) from exc
    except Exception:
        await session.rollback()
        raise


async def _limit(request: Request, auth: AuthenticatedUser, action: str) -> None:
    settings = request.app.state.settings
    try:
        await enforce_rate_limit(
            request.app.state.redis,
            f"{action}:{auth.portal.id}:{auth.user.id}",
            limit=settings.community_rate_limit,
            window_seconds=settings.community_rate_limit_window_seconds,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(429, detail={"code": "RATE_LIMITED"}) from exc


@router.get("/stories/{story_slug}/comments", response_model=CommentPage)
async def comments(
    portal_slug: str,
    story_slug: str,
    session: DatabaseSession,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=500),
) -> CommentPage:
    try:
        return await CommunityService(session).comment_page(portal_slug, story_slug, limit, cursor)
    except (CommunityNotFoundError, CommunityDisabledError, InvalidCursorError) as exc:
        raise _error(exc) from exc


@router.post("/stories/{story_slug}/comments", response_model=CommentView, status_code=201)
async def create_comment(
    story_slug: str,
    payload: CommentCreate,
    request: Request,
    response: Response,
    auth: ProtectedUser,
    session: DatabaseSession,
) -> CommentView:
    await _limit(request, auth, "comment")
    result, created = await _commit(
        session, CommunityService(session).create_comment(auth, story_slug, payload)
    )
    if not created:
        response.status_code = 200
    return result


@router.put("/comments/{comment_id}", response_model=CommentView)
async def update_comment(
    comment_id: UUID, payload: CommentUpdate, auth: ProtectedUser, session: DatabaseSession
) -> CommentView:
    return await _commit(
        session, CommunityService(session).update_comment(auth, comment_id, payload)
    )


@router.delete("/comments/{comment_id}", response_model=ToggleView)
async def remove_comment(
    comment_id: UUID, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(session, CommunityService(session).remove_comment(auth, comment_id))


@router.put("/stories/{story_slug}/reactions", response_model=ToggleView)
async def react_to_story(
    story_slug: str,
    payload: ReactionUpdate,
    request: Request,
    auth: ProtectedUser,
    session: DatabaseSession,
) -> ToggleView:
    await _limit(request, auth, "reaction")
    return await _commit(session, CommunityService(session).react(auth, story_slug, payload))


@router.delete("/stories/{story_slug}/reactions", response_model=ToggleView)
async def remove_story_reaction(
    story_slug: str, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(session, CommunityService(session).remove_reaction(auth, story_slug))


@router.put("/stories/{story_slug}/comments/{comment_id}/reactions", response_model=ToggleView)
async def react_to_comment(
    story_slug: str,
    comment_id: UUID,
    payload: ReactionUpdate,
    request: Request,
    auth: ProtectedUser,
    session: DatabaseSession,
) -> ToggleView:
    await _limit(request, auth, "reaction")
    return await _commit(
        session, CommunityService(session).react(auth, story_slug, payload, comment_id)
    )


@router.delete("/stories/{story_slug}/comments/{comment_id}/reactions", response_model=ToggleView)
async def remove_comment_reaction(
    story_slug: str, comment_id: UUID, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(
        session, CommunityService(session).remove_reaction(auth, story_slug, comment_id)
    )


@router.post("/comments/{comment_id}/reports", response_model=ReportView, status_code=201)
async def report_comment(
    comment_id: UUID, payload: ReportCreate, auth: ProtectedUser, session: DatabaseSession
) -> ReportView:
    return await _commit(session, CommunityService(session).report(auth, comment_id, payload))


@router.put("/stories/{story_slug}/save", response_model=ToggleView)
async def save_story(story_slug: str, auth: ProtectedUser, session: DatabaseSession) -> ToggleView:
    return await _commit(session, CommunityService(session).toggle_save(auth, story_slug, True))


@router.delete("/stories/{story_slug}/save", response_model=ToggleView)
async def unsave_story(
    story_slug: str, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(session, CommunityService(session).toggle_save(auth, story_slug, False))


@router.get("/me/saves", response_model=list[SaveView])
async def my_saves(auth: ReadUser, session: DatabaseSession) -> list[SaveView]:
    return await CommunityService(session).saves(auth)


@router.put("/follows/{target_type}/{target_id}", response_model=ToggleView)
async def follow(
    target_type: FollowTargetType, target_id: UUID, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(
        session, CommunityService(session).toggle_follow(auth, target_type, target_id, True)
    )


@router.delete("/follows/{target_type}/{target_id}", response_model=ToggleView)
async def unfollow(
    target_type: FollowTargetType, target_id: UUID, auth: ProtectedUser, session: DatabaseSession
) -> ToggleView:
    return await _commit(
        session, CommunityService(session).toggle_follow(auth, target_type, target_id, False)
    )


@router.get("/me/follows", response_model=list[FollowView])
async def my_follows(auth: ReadUser, session: DatabaseSession) -> list[FollowView]:
    return await CommunityService(session).follows(auth)


@router.put("/moderation/comments/{comment_id}", response_model=CommentView)
async def moderate(
    comment_id: UUID, payload: ModerationUpdate, auth: ProtectedUser, session: DatabaseSession
) -> CommentView:
    require_moderator(auth)
    return await _commit(session, CommunityService(session).moderate(auth, comment_id, payload))
