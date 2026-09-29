from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.advertising.application.service import (
    AdvertisingConflictError,
    AdvertisingDisabledError,
    AdvertisingNotFoundError,
    AdvertisingService,
    AdvertisingValidationError,
)
from news_platform.modules.advertising.domain.schemas import (
    AdDecision,
    AdvertisingOverview,
    CampaignView,
    CampaignWrite,
    ClickCreate,
    ImpressionCreate,
    PlacementView,
    PlacementWrite,
    TrackingReceipt,
)
from news_platform.modules.users.api.dependencies import admin_csrf_user, admin_user
from news_platform.modules.users.application.service import AuthenticatedUser

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/ads", tags=["advertising"])
admin_router = APIRouter(
    prefix="/api/v1/portals/{portal_slug}/admin/advertising", tags=["advertising-admin"]
)
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]
ReadAdmin = Annotated[AuthenticatedUser, Depends(admin_user)]
WriteAdmin = Annotated[AuthenticatedUser, Depends(admin_csrf_user)]


def _raise(exc: Exception) -> NoReturn:
    if isinstance(exc, AdvertisingDisabledError):
        raise HTTPException(404, detail={"code": "ADVERTISING_DISABLED"}) from exc
    if isinstance(exc, AdvertisingNotFoundError):
        raise HTTPException(404, detail={"code": "ADVERTISING_RESOURCE_NOT_FOUND"}) from exc
    if isinstance(exc, AdvertisingConflictError):
        raise HTTPException(409, detail={"code": "ADVERTISING_IDEMPOTENCY_CONFLICT"}) from exc
    raise HTTPException(422, detail={"code": "ADVERTISING_INVALID", "message": str(exc)}) from exc


@router.get("/placements/{placement_code}", response_model=AdDecision | None)
async def decision(
    portal_slug: str,
    placement_code: str,
    session: DatabaseSession,
    identity_key: Annotated[str, Query(min_length=8, max_length=128)],
    language: Annotated[str, Query(min_length=2, max_length=35)] = "en",
    content_id: UUID | None = None,
    geography_id: UUID | None = None,
    category_id: UUID | None = None,
    content_type: str | None = None,
) -> AdDecision | Response:
    try:
        result = await AdvertisingService(session).decide(
            portal_slug,
            placement_code,
            identity_key,
            language=language,
            content_id=content_id,
            geography_id=geography_id,
            category_id=category_id,
            content_type=content_type,
        )
        return result if result is not None else Response(status_code=204)
    except (
        AdvertisingDisabledError,
        AdvertisingNotFoundError,
        AdvertisingValidationError,
    ) as exc:
        _raise(exc)


@router.post("/impressions", response_model=TrackingReceipt, status_code=202)
async def impression(
    portal_slug: str, payload: ImpressionCreate, session: DatabaseSession
) -> TrackingReceipt:
    try:
        result = await AdvertisingService(session).track_impression(portal_slug, payload)
        await session.commit()
        return result
    except (
        AdvertisingDisabledError,
        AdvertisingNotFoundError,
        AdvertisingConflictError,
        AdvertisingValidationError,
    ) as exc:
        await session.rollback()
        _raise(exc)


@router.post("/clicks", response_model=TrackingReceipt, status_code=202)
async def click(
    portal_slug: str, payload: ClickCreate, session: DatabaseSession
) -> TrackingReceipt:
    try:
        result = await AdvertisingService(session).track_click(portal_slug, payload)
        await session.commit()
        return result
    except (
        AdvertisingDisabledError,
        AdvertisingNotFoundError,
        AdvertisingConflictError,
        AdvertisingValidationError,
    ) as exc:
        await session.rollback()
        _raise(exc)


@admin_router.get("", response_model=AdvertisingOverview)
async def overview(
    portal_slug: str, response: Response, session: DatabaseSession, _admin: ReadAdmin
) -> AdvertisingOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await AdvertisingService(session).overview(portal_slug)
    except AdvertisingNotFoundError as exc:
        _raise(exc)


@admin_router.post("/placements", response_model=PlacementView, status_code=201)
async def create_placement(
    portal_slug: str,
    payload: PlacementWrite,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> PlacementView:
    try:
        result = await AdvertisingService(session).create_placement(
            portal_slug, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (AdvertisingNotFoundError, AdvertisingConflictError) as exc:
        await session.rollback()
        _raise(exc)


@admin_router.put("/placements/{placement_id}", response_model=PlacementView)
async def update_placement(
    portal_slug: str,
    placement_id: UUID,
    payload: PlacementWrite,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> PlacementView:
    try:
        result = await AdvertisingService(session).update_placement(
            portal_slug, placement_id, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (AdvertisingNotFoundError, AdvertisingConflictError) as exc:
        await session.rollback()
        _raise(exc)


@admin_router.post("/campaigns", response_model=CampaignView, status_code=201)
async def create_campaign(
    portal_slug: str,
    payload: CampaignWrite,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> CampaignView:
    try:
        result = await AdvertisingService(session).create_campaign(
            portal_slug, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (
        AdvertisingNotFoundError,
        AdvertisingConflictError,
        AdvertisingValidationError,
    ) as exc:
        await session.rollback()
        _raise(exc)


@admin_router.put("/campaigns/{campaign_id}", response_model=CampaignView)
async def update_campaign(
    portal_slug: str,
    campaign_id: UUID,
    payload: CampaignWrite,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> CampaignView:
    try:
        result = await AdvertisingService(session).update_campaign(
            portal_slug, campaign_id, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (
        AdvertisingNotFoundError,
        AdvertisingConflictError,
        AdvertisingValidationError,
    ) as exc:
        await session.rollback()
        _raise(exc)
