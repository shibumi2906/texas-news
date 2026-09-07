from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.infrastructure.database import get_db_session
from news_platform.modules.public_site.application.service import (
    PublicNotFoundError,
    PublicSiteService,
)
from news_platform.modules.search.application.service import SearchService
from news_platform.modules.search.domain.schemas import (
    InvalidSearchCursorError,
    SearchPage,
    SearchQuery,
)
from news_platform.modules.search.infrastructure.postgres import PostgresSearchBackend

router = APIRouter(prefix="/api/v1/portals/{portal_slug}", tags=["public-search"])


@router.get("/search", response_model=SearchPage)
async def search(
    portal_slug: str,
    query: Annotated[SearchQuery, Query()],
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SearchPage:
    response.headers["Cache-Control"] = "no-store"
    try:
        async with session.begin():
            return await SearchService(
                PublicSiteService(session), PostgresSearchBackend(session)
            ).page(portal_slug, query)
    except PublicNotFoundError as exc:
        raise HTTPException(
            404, detail={"code": "PUBLIC_RESOURCE_NOT_FOUND", "message": str(exc)}
        ) from exc
    except InvalidSearchCursorError as exc:
        raise HTTPException(
            400, detail={"code": "INVALID_SEARCH_CURSOR", "message": str(exc)}
        ) from exc
