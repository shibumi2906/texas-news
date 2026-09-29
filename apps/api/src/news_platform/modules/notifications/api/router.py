from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.notifications.application.service import (
    NotificationsDisabledError,
    NotificationService,
    NotificationsNotFoundError,
)
from news_platform.modules.notifications.domain.schemas import (
    NotificationAdminOverview,
    NotificationMessageCreate,
    NotificationMessageResult,
    SubscriptionResult,
    SubscriptionView,
    SubscriptionWrite,
)
from news_platform.modules.users.api.dependencies import (
    admin_csrf_user,
    admin_user,
    csrf_protected_user,
    current_user,
)
from news_platform.modules.users.application.service import AuthenticatedUser

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/notifications", tags=["notifications"])
admin_router = APIRouter(
    prefix="/api/v1/portals/{portal_slug}/admin/notifications",
    tags=["notifications-admin"],
)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
CurrentUser = Annotated[AuthenticatedUser, Depends(current_user)]
WriteUser = Annotated[AuthenticatedUser, Depends(csrf_protected_user)]
ReadAdmin = Annotated[AuthenticatedUser, Depends(admin_user)]
WriteAdmin = Annotated[AuthenticatedUser, Depends(admin_csrf_user)]


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, NotificationsDisabledError):
        raise HTTPException(404, detail={"code": "NOTIFICATIONS_DISABLED"}) from exc
    raise HTTPException(404, detail={"code": "NOTIFICATION_RESOURCE_NOT_FOUND"}) from exc


@router.get("/subscriptions", response_model=list[SubscriptionView])
async def subscriptions(session: DatabaseSession, auth: CurrentUser) -> list[SubscriptionView]:
    try:
        return await NotificationService(session).list_subscriptions(auth)
    except (NotificationsDisabledError, NotificationsNotFoundError) as exc:
        _raise(exc)


@router.put("/subscriptions", response_model=SubscriptionResult)
async def subscribe(
    payload: SubscriptionWrite, session: DatabaseSession, auth: WriteUser
) -> SubscriptionResult:
    try:
        result = await NotificationService(session).subscribe(auth, payload)
        await session.commit()
        return result
    except (NotificationsDisabledError, NotificationsNotFoundError) as exc:
        await session.rollback()
        _raise(exc)


@router.delete("/subscriptions/{subscription_id}", status_code=204)
async def unsubscribe(subscription_id: UUID, session: DatabaseSession, auth: WriteUser) -> Response:
    try:
        await NotificationService(session).remove_subscription(auth, subscription_id)
        await session.commit()
        return Response(status_code=204)
    except (NotificationsDisabledError, NotificationsNotFoundError) as exc:
        await session.rollback()
        _raise(exc)


@admin_router.get("", response_model=NotificationAdminOverview)
async def admin_overview(
    portal_slug: str, response: Response, session: DatabaseSession, _admin: ReadAdmin
) -> NotificationAdminOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await NotificationService(session).admin_overview(portal_slug)
    except NotificationsNotFoundError as exc:
        _raise(exc)


@admin_router.post("/messages", response_model=NotificationMessageResult, status_code=202)
async def create_message(
    portal_slug: str,
    payload: NotificationMessageCreate,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> NotificationMessageResult:
    try:
        result = await NotificationService(session).create_message(
            portal_slug, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (NotificationsDisabledError, NotificationsNotFoundError) as exc:
        await session.rollback()
        _raise(exc)
