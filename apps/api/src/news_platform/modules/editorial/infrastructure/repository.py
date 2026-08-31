from __future__ import annotations

from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentItem,
    ContentStatus,
    ContentType,
)


class EditorialRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_locked(self, content_id: UUID) -> ContentItem | None:
        return cast(
            ContentItem | None,
            await self.session.scalar(
                select(ContentItem).where(ContentItem.id == content_id).with_for_update()
            ),
        )

    def filtered_statement(
        self,
        *,
        status: ContentStatus | None,
        content_type: ContentType | None,
        source_id: UUID | None,
        category_id: UUID | None,
        text_query: str | None,
    ) -> Select[tuple[ContentItem]]:
        statement = select(ContentItem)
        if category_id is not None:
            statement = statement.join(
                ContentCategory, ContentCategory.content_item_id == ContentItem.id
            ).where(ContentCategory.category_id == category_id)
        if status is not None:
            statement = statement.where(ContentItem.status == status)
        if content_type is not None:
            statement = statement.where(ContentItem.content_type == content_type)
        if source_id is not None:
            statement = statement.where(ContentItem.source_id == source_id)
        if text_query:
            statement = statement.where(ContentItem.title.ilike(f"%{text_query}%"))
        return statement

    async def list(
        self,
        *,
        status: ContentStatus | None,
        content_type: ContentType | None,
        source_id: UUID | None,
        category_id: UUID | None,
        text_query: str | None,
        offset: int,
        limit: int,
    ) -> tuple[list[ContentItem], int]:
        statement = self.filtered_statement(
            status=status,
            content_type=content_type,
            source_id=source_id,
            category_id=category_id,
            text_query=text_query,
        )
        total = await self.session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        items = (
            await self.session.scalars(
                statement.order_by(ContentItem.updated_at.desc(), ContentItem.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return list(items), total or 0
