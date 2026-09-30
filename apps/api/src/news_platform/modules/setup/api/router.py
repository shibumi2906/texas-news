from __future__ import annotations

import hmac
from typing import Annotated, Never

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.setup.application.service import (
    SetupNotFoundError,
    SetupService,
    SetupValidationError,
)
from news_platform.modules.setup.domain.schemas import (
    ConnectionTestResult,
    FeatureSettings,
    IntegrationKind,
    IntegrationWrite,
    PublisherSettings,
    SetupOverview,
    SetupStatus,
)
from news_platform.modules.users.api.dependencies import admin_csrf_user, admin_user
from news_platform.modules.users.api.router import _set_cookie
from news_platform.modules.users.application.service import AuthenticatedUser, AuthService
from news_platform.modules.users.domain.models import User
from news_platform.modules.users.domain.schemas import AuthView, Registration

router = APIRouter(prefix="/api/v1/portals/{portal_slug}", tags=["setup"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
ReadAdmin = Annotated[AuthenticatedUser, Depends(admin_user)]
WriteAdmin = Annotated[AuthenticatedUser, Depends(admin_csrf_user)]


def _service(session: AsyncSession, request: Request) -> SetupService:
    return SetupService(session, request.app.state.settings, request.app.state.redis)


def _raise(exc: SetupNotFoundError | SetupValidationError) -> Never:
    if isinstance(exc, SetupNotFoundError):
        raise HTTPException(404, detail={"code": "PORTAL_NOT_FOUND"}) from exc
    raise HTTPException(422, detail={"code": "SETUP_INVALID", "message": str(exc)}) from exc


@router.post("/setup/bootstrap-admin", response_model=AuthView, status_code=201)
async def bootstrap_admin(
    portal_slug: str,
    payload: Registration,
    request: Request,
    response: Response,
    session: DatabaseSession,
    setup_token: Annotated[str | None, Header(alias="X-Setup-Token")] = None,
) -> AuthView:
    """Create the one-time first owner; closes permanently after the first admin."""
    async with session.begin():
        await session.execute(select(func.pg_advisory_xact_lock(918273645)))
        portal, completed = await SetupService(
            session, request.app.state.settings, request.app.state.redis
        ).status(portal_slug)
        admin_count = await session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if completed or admin_count != 0:
            raise HTTPException(409, detail={"code": "BOOTSTRAP_CLOSED"})
        configured_token = request.app.state.settings.setup_bootstrap_token
        if request.app.state.settings.environment == "production":
            expected = configured_token.get_secret_value() if configured_token else ""
            if not setup_token or not expected or not hmac.compare_digest(setup_token, expected):
                raise HTTPException(403, detail={"code": "BOOTSTRAP_TOKEN_REQUIRED"})
        result, tokens = await AuthService(
            session, request.app.state.settings.auth_session_hours
        ).register(portal_slug, payload)
        user = await session.get(User, result.user.id)
        assert user is not None
        user.role = "admin"
        result.user.role = "admin"
        session.add(
            EditorialAuditLog(
                actor=str(user.id),
                action="setup_admin_bootstrap",
                entity_type="portal_setup",
                entity_id=portal.id,
                before={},
                after={"role": "admin"},
            )
        )
    _set_cookie(
        response,
        tokens.token,
        tokens.csrf,
        tokens.expires_at,
        request.app.state.settings.environment == "production",
    )
    return result


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(
    portal_slug: str, response: Response, request: Request, session: DatabaseSession
) -> SetupStatus:
    response.headers["Cache-Control"] = "no-store"
    try:
        _, completed = await _service(session, request).status(portal_slug)
        return SetupStatus(required=not completed, completed=completed)
    except SetupNotFoundError as exc:
        _raise(exc)


@router.get("/admin/setup", response_model=SetupOverview)
async def setup_overview(
    portal_slug: str,
    response: Response,
    request: Request,
    session: DatabaseSession,
    _admin: ReadAdmin,
) -> SetupOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await _service(session, request).overview(portal_slug)
    except (SetupNotFoundError, SetupValidationError) as exc:
        _raise(exc)


@router.put("/admin/setup/publisher", response_model=SetupOverview)
async def save_publisher(
    portal_slug: str,
    payload: PublisherSettings,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> SetupOverview:
    try:
        result = await _service(session, request).save_publisher(
            portal_slug, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (SetupNotFoundError, SetupValidationError) as exc:
        await session.rollback()
        _raise(exc)


@router.put("/admin/setup/integrations/{kind}", response_model=SetupOverview)
async def save_integration(
    portal_slug: str,
    kind: IntegrationKind,
    payload: IntegrationWrite,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> SetupOverview:
    try:
        result = await _service(session, request).save_integration(
            portal_slug, kind, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (SetupNotFoundError, SetupValidationError) as exc:
        await session.rollback()
        _raise(exc)


@router.put("/admin/setup/features", response_model=SetupOverview)
async def save_features(
    portal_slug: str,
    payload: FeatureSettings,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> SetupOverview:
    try:
        result = await _service(session, request).save_features(
            portal_slug, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (SetupNotFoundError, SetupValidationError) as exc:
        await session.rollback()
        _raise(exc)


@router.post("/admin/setup/integrations/{kind}/test", response_model=ConnectionTestResult)
async def test_integration(
    portal_slug: str,
    kind: IntegrationKind,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> ConnectionTestResult:
    try:
        result = await _service(session, request).test_integration(
            portal_slug, kind, str(admin.user.id)
        )
        await session.commit()
        return result
    except (SetupNotFoundError, SetupValidationError) as exc:
        await session.rollback()
        _raise(exc)


@router.post("/admin/setup/complete", response_model=SetupOverview)
async def complete_setup(
    portal_slug: str,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> SetupOverview:
    try:
        result = await _service(session, request).complete(portal_slug, str(admin.user.id))
        await session.commit()
        return result
    except (SetupNotFoundError, SetupValidationError) as exc:
        await session.rollback()
        _raise(exc)
