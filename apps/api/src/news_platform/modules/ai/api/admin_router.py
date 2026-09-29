from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.ai.application.admin_service import (
    AIAdminNotFoundError,
    AIAdminService,
    AIAdminValidationError,
)
from news_platform.modules.ai.domain.admin_schemas import (
    AIAdminOverview,
    AITaskConfigUpdate,
    ExperimentUpdate,
    PromptVersionCreate,
    PromptVersionView,
)
from news_platform.modules.users.api.dependencies import csrf_protected_user, current_user
from news_platform.modules.users.application.service import AuthenticatedUser

router = APIRouter(prefix="/api/v1/portals/{portal_slug}/admin/ai", tags=["ai-admin"])
DatabaseSession = Annotated[AsyncSession, Depends(get_db_session)]


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


ReadAdmin = Annotated[AuthenticatedUser, Depends(admin_user)]
WriteAdmin = Annotated[AuthenticatedUser, Depends(admin_csrf_user)]


def _service(session: AsyncSession, request: Request) -> AIAdminService:
    return AIAdminService(session, request.app.state.settings)


def _raise_error(exc: AIAdminNotFoundError | AIAdminValidationError) -> NoReturn:
    if isinstance(exc, AIAdminNotFoundError):
        raise HTTPException(404, detail={"code": "AI_ADMIN_RESOURCE_NOT_FOUND"}) from exc
    raise HTTPException(
        422, detail={"code": "AI_ADMIN_INVALID_CONFIGURATION", "message": str(exc)}
    ) from exc


@router.get("", response_model=AIAdminOverview)
async def overview(
    portal_slug: str,
    response: Response,
    request: Request,
    session: DatabaseSession,
    _admin: ReadAdmin,
) -> AIAdminOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        return await _service(session, request).overview(portal_slug)
    except AIAdminNotFoundError as exc:
        _raise_error(exc)


@router.patch("/tasks/{task}", response_model=AIAdminOverview)
async def update_task(
    portal_slug: str,
    task: str,
    payload: AITaskConfigUpdate,
    response: Response,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> AIAdminOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        await _service(session, request).update_task(portal_slug, task, payload, str(admin.user.id))
        await session.commit()
        return await _service(session, request).overview(portal_slug)
    except (AIAdminNotFoundError, AIAdminValidationError) as exc:
        await session.rollback()
        _raise_error(exc)
    except Exception:
        await session.rollback()
        raise


@router.post("/tasks/{task}/prompts", response_model=PromptVersionView, status_code=201)
async def create_prompt(
    portal_slug: str,
    task: str,
    payload: PromptVersionCreate,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> PromptVersionView:
    try:
        result = await _service(session, request).create_prompt(
            portal_slug, task, payload, str(admin.user.id)
        )
        await session.commit()
        return result
    except (AIAdminNotFoundError, AIAdminValidationError) as exc:
        await session.rollback()
        _raise_error(exc)
    except Exception:
        await session.rollback()
        raise


@router.post("/tasks/{task}/prompts/{version_id}/activate", response_model=AIAdminOverview)
async def activate_prompt(
    portal_slug: str,
    task: str,
    version_id: UUID,
    response: Response,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> AIAdminOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        await _service(session, request).activate_prompt(
            portal_slug, task, version_id, str(admin.user.id)
        )
        await session.commit()
        return await _service(session, request).overview(portal_slug)
    except (AIAdminNotFoundError, AIAdminValidationError) as exc:
        await session.rollback()
        _raise_error(exc)
    except Exception:
        await session.rollback()
        raise


@router.put("/experiments/{task}", response_model=AIAdminOverview)
async def update_experiment(
    portal_slug: str,
    task: str,
    payload: ExperimentUpdate,
    response: Response,
    request: Request,
    session: DatabaseSession,
    admin: WriteAdmin,
) -> AIAdminOverview:
    response.headers["Cache-Control"] = "no-store"
    try:
        await _service(session, request).update_experiment(
            portal_slug, task, payload, str(admin.user.id)
        )
        await session.commit()
        return await _service(session, request).overview(portal_slug)
    except (AIAdminNotFoundError, AIAdminValidationError) as exc:
        await session.rollback()
        _raise_error(exc)
    except Exception:
        await session.rollback()
        raise
