from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentItem,
    ContentStatus,
    ContentVersion,
    ContentVersionOrigin,
)
from news_platform.modules.editorial.application.errors import (
    ContentNotFoundError,
    EditorialValidationError,
    PublicationBlockedError,
)
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.editorial.domain.policy import InvalidTransitionError, require_transition
from news_platform.modules.editorial.domain.schemas import EditorialEdit
from news_platform.modules.editorial.infrastructure.repository import EditorialRepository
from news_platform.modules.ingestion.domain.models import IncomingPackage
from news_platform.modules.localization.domain.models import (
    PUBLIC_TRANSLATION_STATUSES,
    Translation,
    TranslationStatus,
)


class EditorialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = EditorialRepository(session)

    async def mark_ready(
        self, content_id: UUID, actor: str, reason: str | None = None
    ) -> ContentItem:
        content = await self._locked(content_id)
        before = self._snapshot(content)
        self._transition(content, ContentStatus.READY)
        await self._audit(content, actor, "ready", before, reason)
        return content

    async def publish(self, content_id: UUID, actor: str, reason: str | None = None) -> ContentItem:
        content = await self._locked(content_id)
        return await self._publish_locked(content, actor, reason)

    async def _publish_locked(
        self, content: ContentItem, actor: str, reason: str | None
    ) -> ContentItem:
        if content.status is ContentStatus.PUBLISHED:
            return content
        await self._require_publishable(content)
        before = self._snapshot(content)
        self._transition(content, ContentStatus.PUBLISHED)
        content.scheduled_at = None
        content.site_published_at = datetime.now(UTC)
        await self._audit(content, actor, "publish", before, reason)
        return content

    async def unpublish(
        self, content_id: UUID, actor: str, reason: str | None = None
    ) -> ContentItem:
        content = await self._locked(content_id)
        before = self._snapshot(content)
        self._transition(content, ContentStatus.UNPUBLISHED)
        await self._audit(content, actor, "unpublish", before, reason)
        return content

    async def schedule(
        self,
        content_id: UUID,
        actor: str,
        scheduled_at: datetime,
        reason: str | None = None,
    ) -> ContentItem:
        if scheduled_at <= datetime.now(UTC):
            raise EditorialValidationError("scheduled_at must be in the future")
        content = await self._locked(content_id)
        await self._require_publishable(content, require_version=True)
        before = self._snapshot(content)
        action = "reschedule" if content.status is ContentStatus.SCHEDULED else "schedule"
        if content.status is not ContentStatus.SCHEDULED:
            self._transition(content, ContentStatus.SCHEDULED)
        content.scheduled_at = scheduled_at
        await self._audit(content, actor, action, before, reason)
        return content

    async def cancel_schedule(
        self, content_id: UUID, actor: str, reason: str | None = None
    ) -> ContentItem:
        content = await self._locked(content_id)
        before = self._snapshot(content)
        self._transition(content, ContentStatus.READY)
        content.scheduled_at = None
        await self._audit(content, actor, "cancel_schedule", before, reason)
        return content

    async def restore(self, content_id: UUID, actor: str, reason: str | None = None) -> ContentItem:
        content = await self._locked(content_id)
        self._require_source_allows_editorial(content)
        if content.status is ContentStatus.UNPUBLISHED:
            await self._require_publishable(content)
            before = self._snapshot(content)
            self._transition(content, ContentStatus.PUBLISHED)
            content.scheduled_at = None
            content.site_published_at = datetime.now(UTC)
            await self._audit(content, actor, "restore", before, reason)
            return content
        if content.status not in {ContentStatus.ARCHIVED, ContentStatus.RETRACTED}:
            raise EditorialValidationError(f"cannot restore content from {content.status.value}")
        before = self._snapshot(content)
        self._transition(content, ContentStatus.READY)
        content.scheduled_at = None
        await self._audit(content, actor, "restore", before, reason)
        return content

    async def edit(self, content_id: UUID, actor: str, edit: EditorialEdit) -> ContentItem:
        content = await self._locked(content_id)
        if content.status is ContentStatus.DELETED:
            raise EditorialValidationError("deleted content cannot be edited")
        before = self._snapshot(content)
        changes = edit.model_dump(exclude_unset=True, exclude={"reason"})
        for field, value in changes.items():
            setattr(content, field, value)
        if not content.title.strip():
            raise EditorialValidationError("title must not be empty")
        current_number = await self.session.scalar(
            select(func.coalesce(func.max(ContentVersion.version_number), 0)).where(
                ContentVersion.content_item_id == content.id
            )
        )
        upstream_version = await self.session.scalar(
            select(IncomingPackage.latest_version).where(
                IncomingPackage.content_item_id == content.id
            )
        )
        self.session.add(
            ContentVersion(
                content_item_id=content.id,
                version_number=(current_number or 0) + 1,
                source_revision=None,
                origin=ContentVersionOrigin.EDITORIAL,
                title=content.title,
                description=content.description,
                body=content.body,
                metadata_={
                    "subtitle": content.subtitle,
                    "actor": actor,
                    "based_on_upstream_version": upstream_version,
                },
                change_reason=edit.reason,
            )
        )
        content.has_editorial_override = True
        await self.session.execute(
            update(Translation)
            .where(
                Translation.content_item_id == content.id,
                Translation.status.in_(PUBLIC_TRANSLATION_STATUSES),
            )
            .values(status=TranslationStatus.OUTDATED)
        )
        await self._audit(content, actor, "edit", before, edit.reason)
        await self.session.flush()
        return content

    async def publish_due(self, batch_size: int, actor: str = "system:scheduler") -> int:
        due = (
            await self.session.scalars(
                select(ContentItem)
                .where(
                    ContentItem.status == ContentStatus.SCHEDULED,
                    ContentItem.scheduled_at <= datetime.now(UTC),
                )
                .order_by(ContentItem.scheduled_at, ContentItem.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        published = 0
        for content in due:
            if not self._is_due_for_publication(content):
                continue
            try:
                await self._publish_locked(content, actor, "scheduled publication")
                published += 1
            except (PublicationBlockedError, EditorialValidationError):
                before = self._snapshot(content)
                if content.upstream_status in {
                    ContentStatus.RETRACTED,
                    ContentStatus.DELETED,
                }:
                    content.status = content.upstream_status
                elif content.status is ContentStatus.SCHEDULED:
                    content.status = ContentStatus.READY
                content.scheduled_at = None
                await self._audit(
                    content,
                    actor,
                    "cancel_schedule",
                    before,
                    "scheduled publication became ineligible",
                )
        return published

    @staticmethod
    def _is_due_for_publication(content: ContentItem) -> bool:
        return (
            content.status is ContentStatus.SCHEDULED
            and content.scheduled_at is not None
            and content.scheduled_at <= datetime.now(UTC)
        )

    async def _require_publishable(
        self, content: ContentItem, *, require_version: bool = True
    ) -> None:
        self._require_source_allows_editorial(content)
        if not content.title.strip():
            raise PublicationBlockedError("content title is required")
        if require_version:
            version_exists = await self.session.scalar(
                select(ContentVersion.id)
                .where(ContentVersion.content_item_id == content.id)
                .limit(1)
            )
            if version_exists is None:
                raise PublicationBlockedError("content has no current version")

    @staticmethod
    def _require_source_allows_editorial(content: ContentItem) -> None:
        if content.upstream_status is ContentStatus.DELETED:
            raise PublicationBlockedError("upstream deleted content is not publishable")
        if content.upstream_status is ContentStatus.RETRACTED:
            raise PublicationBlockedError("upstream retracted content is not publishable")

    async def _locked(self, content_id: UUID) -> ContentItem:
        content = await self.repository.get_locked(content_id)
        if content is None:
            raise ContentNotFoundError("content item not found")
        return content

    @staticmethod
    def _transition(content: ContentItem, target: ContentStatus) -> None:
        try:
            require_transition(content.status, target)
        except InvalidTransitionError as exc:
            raise EditorialValidationError(str(exc)) from exc
        content.status = target

    async def _audit(
        self,
        content: ContentItem,
        actor: str,
        action: str,
        before: dict[str, Any],
        reason: str | None,
    ) -> None:
        self.session.add(
            EditorialAuditLog(
                actor=actor,
                action=action,
                entity_type="content_item",
                entity_id=content.id,
                before=before,
                after=self._snapshot(content),
                reason=reason,
            )
        )
        await self.session.flush()

    @staticmethod
    def _snapshot(content: ContentItem) -> dict[str, Any]:
        return {
            "status": content.status.value,
            "upstream_status": content.upstream_status.value,
            "title": content.title,
            "subtitle": content.subtitle,
            "description": content.description,
            "body": content.body,
            "scheduled_at": content.scheduled_at.isoformat() if content.scheduled_at else None,
            "site_published_at": (
                content.site_published_at.isoformat() if content.site_published_at else None
            ),
            "has_editorial_override": content.has_editorial_override,
        }
