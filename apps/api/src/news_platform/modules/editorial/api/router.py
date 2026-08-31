from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.content.domain.models import ContentItem, ContentStatus, ContentType
from news_platform.modules.editorial.application.errors import EditorialError
from news_platform.modules.editorial.application.service import EditorialService
from news_platform.modules.editorial.domain.schemas import (
    ContentAdminPage,
    ContentAdminView,
    EditorialCommand,
    EditorialEdit,
    ScheduleCommand,
)
from news_platform.modules.editorial.infrastructure.repository import EditorialRepository

router = APIRouter(prefix="/api/v1/admin/content", tags=["editorial-admin"])
DatabaseSession = Depends(get_db_session)


def require_actor(value: str | None = Header(default=None, alias="X-Editorial-Actor")) -> str:
    if not value or not value.strip():
        raise HTTPException(401, detail={"code": "EDITORIAL_ACTOR_REQUIRED"})
    return value.strip()[:255]


Actor = Depends(require_actor)


def raise_editorial_error(exc: EditorialError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.get("", response_model=ContentAdminPage)
async def list_content(
    session: AsyncSession = DatabaseSession,
    _actor: str = Actor,
    status: ContentStatus | None = None,
    content_type: ContentType | None = None,
    source_id: UUID | None = None,
    category_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> ContentAdminPage:
    items, total = await EditorialRepository(session).list(
        status=status,
        content_type=content_type,
        source_id=source_id,
        category_id=category_id,
        text_query=q,
        offset=offset,
        limit=limit,
    )
    return ContentAdminPage(
        items=[ContentAdminView.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{content_id}", response_model=ContentAdminView)
async def get_content(
    content_id: UUID,
    session: AsyncSession = DatabaseSession,
    _actor: str = Actor,
) -> ContentAdminView:
    content = await session.get(ContentItem, content_id)
    if content is None:
        raise HTTPException(404, detail={"code": "CONTENT_NOT_FOUND"})
    return ContentAdminView.model_validate(content)


async def execute(
    session: AsyncSession,
    operation: str,
    content_id: UUID,
    actor: str,
    payload: EditorialCommand | ScheduleCommand | EditorialEdit,
) -> ContentAdminView:
    service = EditorialService(session)
    try:
        async with session.begin():
            if operation == "ready":
                content = await service.mark_ready(content_id, actor, payload.reason)
            elif operation == "publish":
                content = await service.publish(content_id, actor, payload.reason)
            elif operation == "unpublish":
                content = await service.unpublish(content_id, actor, payload.reason)
            elif operation == "schedule" and isinstance(payload, ScheduleCommand):
                content = await service.schedule(
                    content_id, actor, payload.scheduled_at, payload.reason
                )
            elif operation == "cancel_schedule":
                content = await service.cancel_schedule(content_id, actor, payload.reason)
            elif operation == "restore":
                content = await service.restore(content_id, actor, payload.reason)
            elif operation == "edit" and isinstance(payload, EditorialEdit):
                content = await service.edit(content_id, actor, payload)
            else:
                raise RuntimeError("unsupported editorial operation")
    except EditorialError as exc:
        raise_editorial_error(exc)
    return ContentAdminView.model_validate(content)


@router.post("/{content_id}/ready", response_model=ContentAdminView)
async def mark_ready(
    content_id: UUID,
    payload: EditorialCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "ready", content_id, actor, payload)


@router.post("/{content_id}/publish", response_model=ContentAdminView)
async def publish(
    content_id: UUID,
    payload: EditorialCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "publish", content_id, actor, payload)


@router.post("/{content_id}/unpublish", response_model=ContentAdminView)
async def unpublish(
    content_id: UUID,
    payload: EditorialCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "unpublish", content_id, actor, payload)


@router.post("/{content_id}/schedule", response_model=ContentAdminView)
async def schedule(
    content_id: UUID,
    payload: ScheduleCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "schedule", content_id, actor, payload)


@router.post("/{content_id}/cancel-schedule", response_model=ContentAdminView)
async def cancel_schedule(
    content_id: UUID,
    payload: EditorialCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "cancel_schedule", content_id, actor, payload)


@router.post("/{content_id}/restore", response_model=ContentAdminView)
async def restore(
    content_id: UUID,
    payload: EditorialCommand,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "restore", content_id, actor, payload)


@router.patch("/{content_id}", response_model=ContentAdminView)
async def edit(
    content_id: UUID,
    payload: EditorialEdit,
    session: AsyncSession = DatabaseSession,
    actor: str = Actor,
) -> ContentAdminView:
    return await execute(session, "edit", content_id, actor, payload)
