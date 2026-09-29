from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.users.application.security import token_digest
from news_platform.modules.users.application.service import (
    AuthenticatedUser,
    AuthenticationError,
    AuthService,
)

SESSION_COOKIE = "news_session"
CSRF_COOKIE = "news_csrf"


async def current_user(
    portal_slug: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> AuthenticatedUser:
    try:
        return await AuthService(session).authenticate(portal_slug, token)
    except AuthenticationError as exc:
        raise HTTPException(401, detail={"code": "AUTHENTICATION_REQUIRED"}) from exc


async def csrf_protected_user(
    request: Request,
    auth: Annotated[AuthenticatedUser, Depends(current_user)],
    csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthenticatedUser:
    origin = request.headers.get("origin")
    if origin is not None:
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        allowed = {
            value.strip().rstrip("/")
            for value in request.app.state.settings.auth_allowed_origins.split(",")
            if value.strip()
        }
        allowed.add(expected.rstrip("/"))
        if origin.rstrip("/") not in allowed:
            raise HTTPException(403, detail={"code": "CSRF_FAILED"})
    if not csrf_token or not hmac.compare_digest(token_digest(csrf_token), auth.session.csrf_hash):
        raise HTTPException(403, detail={"code": "CSRF_FAILED"})
    return auth


def require_moderator(auth: AuthenticatedUser) -> AuthenticatedUser:
    if auth.user.role not in {"moderator", "admin"}:
        raise HTTPException(403, detail={"code": "MODERATOR_REQUIRED"})
    return auth


async def admin_user(
    auth: Annotated[AuthenticatedUser, Depends(current_user)],
) -> AuthenticatedUser:
    if auth.user.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    return auth


async def admin_csrf_user(
    auth: Annotated[AuthenticatedUser, Depends(csrf_protected_user)],
) -> AuthenticatedUser:
    if auth.user.role != "admin":
        raise HTTPException(403, detail={"code": "ADMIN_REQUIRED"})
    return auth
