from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.users.api.dependencies import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    csrf_protected_user,
    current_user,
)
from news_platform.modules.users.application.rate_limit import (
    RateLimitExceededError,
    enforce_rate_limit,
)
from news_platform.modules.users.application.service import (
    AccountConflictError,
    AuthenticatedUser,
    AuthenticationError,
    AuthService,
    PortalNotFoundError,
    user_view,
)
from news_platform.modules.users.domain.schemas import (
    AuthView,
    Credentials,
    LogoutView,
    ProfileUpdate,
    Registration,
    UserView,
)

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/auth", tags=["authentication"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


def _rate_identity(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    return hashlib.sha256(address.encode()).hexdigest()[:24]


def _set_cookie(
    response: Response, token: str, csrf: str, expires_at: datetime, production: bool
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=production,
        samesite="lax",
        path="/api/v1/portals/",
        expires=expires_at,
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,
        secure=production,
        samesite="lax",
        path="/",
        expires=expires_at,
    )
    response.headers["Cache-Control"] = "no-store"


async def _login_limit(request: Request, portal_slug: str) -> None:
    settings = request.app.state.settings
    try:
        await enforce_rate_limit(
            request.app.state.redis,
            f"login:{portal_slug}:{_rate_identity(request)}",
            limit=settings.auth_login_rate_limit,
            window_seconds=settings.auth_rate_limit_window_seconds,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(429, detail={"code": "RATE_LIMITED"}) from exc


@router.post("/register", response_model=AuthView, status_code=201)
async def register(
    portal_slug: str,
    payload: Registration,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AuthView:
    await _login_limit(request, portal_slug)
    try:
        async with session.begin():
            result, tokens = await AuthService(
                session, request.app.state.settings.auth_session_hours
            ).register(portal_slug, payload)
        _set_cookie(
            response,
            tokens.token,
            tokens.csrf,
            tokens.expires_at,
            request.app.state.settings.environment == "production",
        )
        return result
    except (AccountConflictError, IntegrityError) as exc:
        raise HTTPException(409, detail={"code": "ACCOUNT_UNAVAILABLE"}) from exc
    except PortalNotFoundError as exc:
        raise HTTPException(404, detail={"code": "PORTAL_NOT_FOUND"}) from exc


@router.post("/login", response_model=AuthView)
async def login(
    portal_slug: str,
    payload: Credentials,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AuthView:
    await _login_limit(request, portal_slug)
    try:
        async with session.begin():
            result, tokens = await AuthService(
                session, request.app.state.settings.auth_session_hours
            ).login(portal_slug, str(payload.email), payload.password)
        _set_cookie(
            response,
            tokens.token,
            tokens.csrf,
            tokens.expires_at,
            request.app.state.settings.environment == "production",
        )
        return result
    except AuthenticationError as exc:
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS"}) from exc
    except PortalNotFoundError as exc:
        raise HTTPException(404, detail={"code": "PORTAL_NOT_FOUND"}) from exc


@router.get("/me", response_model=UserView)
async def me(
    response: Response, auth: Annotated[AuthenticatedUser, Depends(current_user)]
) -> UserView:
    response.headers["Cache-Control"] = "no-store"
    return user_view(auth.user, auth.profile)


@router.put("/profile", response_model=UserView)
async def update_profile(
    payload: ProfileUpdate,
    response: Response,
    auth: Annotated[AuthenticatedUser, Depends(csrf_protected_user)],
    session: DatabaseSession,
) -> UserView:
    try:
        result = await AuthService(session).update_profile(auth, payload)
        await session.commit()
        response.headers["Cache-Control"] = "no-store"
        return result
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(422, detail={"code": "INVALID_PROFILE"}) from exc
    except Exception:
        await session.rollback()
        raise


@router.post("/logout", response_model=LogoutView)
async def logout(
    response: Response,
    auth: Annotated[AuthenticatedUser, Depends(csrf_protected_user)],
    session: DatabaseSession,
) -> LogoutView:
    try:
        auth.session.revoked_at = datetime.now(UTC)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    response.delete_cookie(SESSION_COOKIE, path="/api/v1/portals/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return LogoutView()
