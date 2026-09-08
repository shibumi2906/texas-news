from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.analytics.domain.models import BehaviorEvent
from news_platform.modules.community.domain.models import (
    Comment,
    CommentReport,
    CommentStatus,
    Follow,
    FollowTargetType,
    ModerationAuditLog,
    Reaction,
    ReactionType,
    Save,
)
from news_platform.modules.community.domain.schemas import (
    CommentCreate,
    CommentPage,
    CommentUpdate,
    CommentView,
    FollowView,
    ModerationUpdate,
    ReactionUpdate,
    ReportCreate,
    ReportView,
    SaveView,
    ToggleView,
)
from news_platform.modules.content.domain.models import ContentEntity, ContentItem, ContentTopic
from news_platform.modules.engagement.domain.models import ContentEngagementCounter
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository
from news_platform.modules.users.application.service import AuthenticatedUser
from news_platform.modules.users.domain.models import UserProfile


class CommunityNotFoundError(Exception):
    pass


class CommunityConflictError(Exception):
    pass


class CommunityForbiddenError(Exception):
    pass


class CommunityDisabledError(Exception):
    pass


class InvalidCursorError(Exception):
    pass


def _cursor(portal_id: UUID, content_id: UUID, created_at: datetime, item_id: UUID) -> str:
    raw = json.dumps(
        [str(portal_id), str(content_id), created_at.isoformat(), str(item_id)],
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(value: str, portal_id: UUID, content_id: UUID) -> tuple[datetime, UUID]:
    try:
        cursor_portal, cursor_content, created, item_id = json.loads(
            base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        )
        if UUID(cursor_portal) != portal_id or UUID(cursor_content) != content_id:
            raise ValueError
        moment = datetime.fromisoformat(created)
        if moment.tzinfo is None:
            raise ValueError
        return moment, UUID(item_id)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError from exc


class CommunityService:
    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)

    async def portal(self, slug: str) -> Portal:
        portal = await self.session.scalar(
            select(Portal).where(Portal.slug == slug, Portal.status == PortalStatus.ACTIVE)
        )
        if portal is None:
            raise CommunityNotFoundError
        if portal.feature_flags.get("community") is False:
            raise CommunityDisabledError
        return portal

    async def public_story(self, portal: Portal, slug: str) -> ContentItem:
        self._ensure_enabled(portal)
        story = await self.session.scalar(
            PublicSiteRepository(self.session)
            .eligible_statement(portal, self.now)
            .where(ContentItem.slug == slug)
        )
        if story is None:
            raise CommunityNotFoundError
        return cast(ContentItem, story)

    async def comment_page(
        self, portal_slug: str, story_slug: str, limit: int, cursor: str | None
    ) -> CommentPage:
        portal = await self.portal(portal_slug)
        story = await self.public_story(portal, story_slug)
        statement = (
            select(Comment, UserProfile.display_name)
            .join(UserProfile, UserProfile.user_id == Comment.user_id)
            .where(
                Comment.portal_id == portal.id,
                Comment.content_id == story.id,
                Comment.status == CommentStatus.VISIBLE,
            )
            .order_by(Comment.created_at, Comment.id)
            .limit(limit + 1)
        )
        if cursor:
            moment, item_id = _decode_cursor(cursor, portal.id, story.id)
            statement = statement.where(
                tuple_(Comment.created_at, Comment.id) > tuple_(literal(moment), literal(item_id))
            )
        rows = list((await self.session.execute(statement)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [self._comment_view(comment, name) for comment, name in rows]
        next_cursor = (
            _cursor(portal.id, story.id, rows[-1][0].created_at, rows[-1][0].id)
            if has_more
            else None
        )
        return CommentPage(items=items, next_cursor=next_cursor)

    async def create_comment(
        self, auth: AuthenticatedUser, story_slug: str, payload: CommentCreate
    ) -> tuple[CommentView, bool]:
        story = await self.public_story(auth.portal, story_slug)
        body = payload.body.strip()
        if not body:
            raise CommunityConflictError
        if payload.parent_id:
            parent = await self.session.get(Comment, payload.parent_id)
            if (
                parent is None
                or parent.portal_id != auth.portal.id
                or parent.content_id != story.id
                or parent.status != CommentStatus.VISIBLE
            ):
                raise CommunityNotFoundError
        inserted = await self.session.scalar(
            pg_insert(Comment)
            .values(
                id=payload.id,
                portal_id=auth.portal.id,
                content_id=story.id,
                user_id=auth.user.id,
                parent_id=payload.parent_id,
                body=body,
                status=CommentStatus.VISIBLE.value,
                score=0,
            )
            .on_conflict_do_nothing(index_elements=[Comment.id])
            .returning(Comment.id)
        )
        if inserted is None:
            existing = await self.session.get(Comment, payload.id)
            if existing is None or (
                existing.portal_id,
                existing.content_id,
                existing.user_id,
                existing.parent_id,
                existing.body,
            ) != (auth.portal.id, story.id, auth.user.id, payload.parent_id, body):
                raise CommunityConflictError
            return self._comment_view(existing, auth.profile.display_name), False
        comment = await self.session.get(Comment, payload.id)
        if comment is None:
            raise RuntimeError("comment disappeared")
        await self._adjust(story.id, "comments", 1)
        self._event(auth, "comment", story.id)
        return self._comment_view(comment, auth.profile.display_name), True

    async def update_comment(
        self, auth: AuthenticatedUser, comment_id: UUID, payload: CommentUpdate
    ) -> CommentView:
        comment = await self._owned_comment(auth, comment_id)
        if comment.status in {CommentStatus.REMOVED, CommentStatus.BLOCKED}:
            raise CommunityConflictError
        comment.body = payload.body.strip()
        await self.session.flush()
        await self.session.refresh(comment)
        return self._comment_view(comment, auth.profile.display_name)

    async def remove_comment(self, auth: AuthenticatedUser, comment_id: UUID) -> ToggleView:
        comment = await self._owned_comment(auth, comment_id)
        if comment.status == CommentStatus.REMOVED:
            return ToggleView(active=False, status="unchanged")
        was_visible = comment.status == CommentStatus.VISIBLE
        comment.status = CommentStatus.REMOVED
        comment.body = "[removed]"
        if was_visible:
            await self._adjust(comment.content_id, "comments", -1)
        return ToggleView(active=False, status="removed")

    async def react(
        self,
        auth: AuthenticatedUser,
        story_slug: str,
        payload: ReactionUpdate,
        comment_id: UUID | None = None,
    ) -> ToggleView:
        story = await self.public_story(auth.portal, story_slug)
        await self._lock(f"reaction:{auth.portal.id}:{auth.user.id}:{comment_id or story.id}")
        if comment_id:
            comment = await self.session.get(Comment, comment_id)
            if (
                comment is None
                or comment.portal_id != auth.portal.id
                or comment.content_id != story.id
                or comment.status != CommentStatus.VISIBLE
            ):
                raise CommunityNotFoundError
        existing = await self.session.scalar(
            select(Reaction).where(
                Reaction.portal_id == auth.portal.id,
                Reaction.user_id == auth.user.id,
                Reaction.comment_id == comment_id
                if comment_id
                else Reaction.content_id == story.id,
            )
        )
        if existing:
            if existing.reaction_type == payload.reaction_type:
                return ToggleView(active=True, status="unchanged")
            was_like = existing.reaction_type == ReactionType.LIKE
            existing.reaction_type = payload.reaction_type
            if comment_id and was_like != (payload.reaction_type == ReactionType.LIKE):
                await self._comment_score(
                    comment_id, 1 if payload.reaction_type == ReactionType.LIKE else -1
                )
            elif not comment_id and was_like != (payload.reaction_type == ReactionType.LIKE):
                await self._adjust(
                    story.id, "likes", 1 if payload.reaction_type == ReactionType.LIKE else -1
                )
            return ToggleView(active=True, status="updated")
        self.session.add(
            Reaction(
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                content_id=None if comment_id else story.id,
                comment_id=comment_id,
                reaction_type=payload.reaction_type,
            )
        )
        if payload.reaction_type == ReactionType.LIKE:
            if comment_id:
                await self._comment_score(comment_id, 1)
            else:
                await self._adjust(story.id, "likes", 1)
        self._event(
            auth, "like" if payload.reaction_type == ReactionType.LIKE else "reaction", story.id
        )
        return ToggleView(active=True, status="created")

    async def remove_reaction(
        self, auth: AuthenticatedUser, story_slug: str, comment_id: UUID | None = None
    ) -> ToggleView:
        story = await self.public_story(auth.portal, story_slug)
        await self._lock(f"reaction:{auth.portal.id}:{auth.user.id}:{comment_id or story.id}")
        if comment_id:
            await self._visible_comment(auth.portal, story.id, comment_id)
        existing = await self.session.scalar(
            select(Reaction)
            .where(
                Reaction.portal_id == auth.portal.id,
                Reaction.user_id == auth.user.id,
                Reaction.comment_id == comment_id
                if comment_id
                else Reaction.content_id == story.id,
            )
            .with_for_update()
        )
        if existing is None:
            return ToggleView(active=False, status="unchanged")
        if existing.reaction_type == ReactionType.LIKE:
            if comment_id:
                await self._comment_score(comment_id, -1)
            else:
                await self._adjust(story.id, "likes", -1)
        await self.session.delete(existing)
        return ToggleView(active=False, status="removed")

    async def report(
        self, auth: AuthenticatedUser, comment_id: UUID, payload: ReportCreate
    ) -> ReportView:
        self._ensure_enabled(auth.portal)
        comment = await self.session.get(Comment, comment_id)
        if (
            comment is None
            or comment.portal_id != auth.portal.id
            or comment.status != CommentStatus.VISIBLE
        ):
            raise CommunityNotFoundError
        await self._public_content_id(auth.portal, comment.content_id)
        report_id = await self.session.scalar(
            pg_insert(CommentReport)
            .values(
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                comment_id=comment_id,
                reason=payload.reason,
                details=payload.details,
            )
            .on_conflict_do_nothing(constraint="uq_comment_reports_user_comment")
            .returning(CommentReport.id)
        )
        if report_id is None:
            existing = await self.session.scalar(
                select(CommentReport).where(
                    CommentReport.portal_id == auth.portal.id,
                    CommentReport.user_id == auth.user.id,
                    CommentReport.comment_id == comment_id,
                )
            )
            if (
                existing is None
                or existing.reason != payload.reason
                or existing.details != payload.details
            ):
                raise CommunityConflictError
            return ReportView(id=existing.id, status="duplicate")
        return ReportView(id=report_id, status="created")

    async def toggle_save(
        self, auth: AuthenticatedUser, story_slug: str, active: bool
    ) -> ToggleView:
        story = await self.public_story(auth.portal, story_slug)
        await self._lock(f"save:{auth.portal.id}:{auth.user.id}:{story.id}")
        existing = await self.session.scalar(
            select(Save)
            .where(
                Save.portal_id == auth.portal.id,
                Save.user_id == auth.user.id,
                Save.content_id == story.id,
            )
            .with_for_update()
        )
        if active and existing is None:
            self.session.add(
                Save(portal_id=auth.portal.id, user_id=auth.user.id, content_id=story.id)
            )
            await self._adjust(story.id, "saves", 1)
            self._event(auth, "save", story.id)
            return ToggleView(active=True, status="created")
        if not active and existing is not None:
            await self.session.delete(existing)
            await self._adjust(story.id, "saves", -1)
            return ToggleView(active=False, status="removed")
        return ToggleView(active=active, status="unchanged")

    async def saves(self, auth: AuthenticatedUser) -> list[SaveView]:
        self._ensure_enabled(auth.portal)
        eligible_ids = (
            PublicSiteRepository(self.session)
            .eligible_statement(auth.portal, self.now)
            .with_only_columns(ContentItem.id)
        )
        rows = list(
            (
                await self.session.scalars(
                    select(Save)
                    .where(
                        Save.portal_id == auth.portal.id,
                        Save.user_id == auth.user.id,
                        Save.content_id.in_(eligible_ids),
                    )
                    .order_by(Save.created_at.desc(), Save.id.desc())
                )
            ).all()
        )
        return [SaveView(content_id=row.content_id, created_at=row.created_at) for row in rows]

    async def toggle_follow(
        self, auth: AuthenticatedUser, target_type: FollowTargetType, target_id: UUID, active: bool
    ) -> ToggleView:
        self._ensure_enabled(auth.portal)
        await self._validate_follow(auth.portal, target_type, target_id)
        await self._lock(f"follow:{auth.portal.id}:{auth.user.id}:{target_type.value}:{target_id}")
        existing = await self.session.scalar(
            select(Follow)
            .where(
                Follow.portal_id == auth.portal.id,
                Follow.user_id == auth.user.id,
                Follow.target_type == target_type,
                Follow.target_id == target_id,
            )
            .with_for_update()
        )
        if active and existing is None:
            self.session.add(
                Follow(
                    portal_id=auth.portal.id,
                    user_id=auth.user.id,
                    target_type=target_type,
                    target_id=target_id,
                )
            )
            self._event(auth, "follow", None)
            return ToggleView(active=True, status="created")
        if not active and existing is not None:
            await self.session.delete(existing)
            return ToggleView(active=False, status="removed")
        return ToggleView(active=active, status="unchanged")

    async def follows(self, auth: AuthenticatedUser) -> list[FollowView]:
        self._ensure_enabled(auth.portal)
        rows = list(
            (
                await self.session.scalars(
                    select(Follow)
                    .where(Follow.portal_id == auth.portal.id, Follow.user_id == auth.user.id)
                    .order_by(Follow.created_at.desc(), Follow.id.desc())
                )
            ).all()
        )
        return [
            FollowView(
                target_type=row.target_type, target_id=row.target_id, created_at=row.created_at
            )
            for row in rows
        ]

    async def moderate(
        self, auth: AuthenticatedUser, comment_id: UUID, payload: ModerationUpdate
    ) -> CommentView:
        self._ensure_enabled(auth.portal)
        comment = await self.session.get(Comment, comment_id, with_for_update=True)
        if comment is None or comment.portal_id != auth.portal.id:
            raise CommunityNotFoundError
        await self._public_content_id(auth.portal, comment.content_id)
        was_visible = comment.status == CommentStatus.VISIBLE
        becomes_visible = payload.status == CommentStatus.VISIBLE
        previous_status = comment.status
        comment.status = payload.status
        if was_visible != becomes_visible:
            await self._adjust(comment.content_id, "comments", 1 if becomes_visible else -1)
        self.session.add(
            ModerationAuditLog(
                portal_id=auth.portal.id,
                moderator_user_id=auth.user.id,
                comment_id=comment.id,
                previous_status=previous_status,
                new_status=payload.status,
            )
        )
        await self.session.flush()
        await self.session.refresh(comment)
        profile = await self.session.get(UserProfile, comment.user_id)
        return self._comment_view(comment, profile.display_name if profile else "User")

    async def _owned_comment(self, auth: AuthenticatedUser, comment_id: UUID) -> Comment:
        self._ensure_enabled(auth.portal)
        comment = await self.session.get(Comment, comment_id, with_for_update=True)
        if comment is None or comment.portal_id != auth.portal.id:
            raise CommunityNotFoundError
        if comment.user_id != auth.user.id:
            raise CommunityForbiddenError
        await self._public_content_id(auth.portal, comment.content_id)
        return comment

    async def _visible_comment(self, portal: Portal, content_id: UUID, comment_id: UUID) -> Comment:
        comment = await self.session.get(Comment, comment_id)
        if (
            comment is None
            or comment.portal_id != portal.id
            or comment.content_id != content_id
            or comment.status != CommentStatus.VISIBLE
        ):
            raise CommunityNotFoundError
        return comment

    def _ensure_enabled(self, portal: Portal) -> None:
        if portal.feature_flags.get("community") is False:
            raise CommunityDisabledError

    async def _public_content_id(self, portal: Portal, content_id: UUID) -> ContentItem:
        content = await self.session.scalar(
            PublicSiteRepository(self.session)
            .eligible_statement(portal, self.now)
            .where(ContentItem.id == content_id)
        )
        if content is None:
            raise CommunityNotFoundError
        return cast(ContentItem, content)

    async def _validate_follow(
        self, portal: Portal, target_type: FollowTargetType, target_id: UUID
    ) -> None:
        eligible_ids = (
            PublicSiteRepository(self.session)
            .eligible_statement(portal, self.now)
            .with_only_columns(ContentItem.id)
        )
        if target_type == FollowTargetType.ENTITY:
            found = (
                await self.session.scalar(
                    select(ContentEntity.entity_id)
                    .where(
                        ContentEntity.entity_id == target_id,
                        ContentEntity.content_item_id.in_(eligible_ids),
                    )
                    .limit(1)
                )
                is not None
            )
        elif target_type == FollowTargetType.TOPIC:
            found = (
                await self.session.scalar(
                    select(ContentTopic.topic_id)
                    .where(
                        ContentTopic.topic_id == target_id,
                        ContentTopic.content_item_id.in_(eligible_ids),
                    )
                    .limit(1)
                )
                is not None
            )
        else:
            geography = await self.session.get(GeographyNode, target_id)
            found = False
            if geography is not None and portal.primary_geography_id:
                scope = (
                    select(GeographyNode.id)
                    .where(GeographyNode.id == portal.primary_geography_id)
                    .cte(recursive=True)
                )
                scope = scope.union_all(
                    select(GeographyNode.id).join(scope, GeographyNode.parent_id == scope.c.id)
                )
                found = (
                    await self.session.scalar(select(scope.c.id).where(scope.c.id == target_id))
                    is not None
                )
        if not found:
            raise CommunityNotFoundError

    async def _adjust(self, content_id: UUID, column_name: str, delta: int) -> None:
        column = getattr(ContentEngagementCounter, column_name)
        await self.session.execute(
            pg_insert(ContentEngagementCounter)
            .values(content_item_id=content_id, **{column_name: max(delta, 0)})
            .on_conflict_do_update(
                index_elements=[ContentEngagementCounter.content_item_id],
                set_={column_name: func.greatest(0, column + delta), "updated_at": func.now()},
            )
        )

    async def _lock(self, key: str) -> None:
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0)))
        )

    async def _comment_score(self, comment_id: UUID, delta: int) -> None:
        await self.session.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(score=func.greatest(0, Comment.score + delta))
        )

    def _event(self, auth: AuthenticatedUser, event_type: str, content_id: UUID | None) -> None:
        self.session.add(
            BehaviorEvent(
                id=uuid4(),
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                anonymous_id=None,
                session_id=str(auth.session.id),
                event_type=event_type,
                content_id=content_id,
                entity_id=None,
                geography_id=None,
                timestamp=self.now,
                properties={},
            )
        )

    @staticmethod
    def _comment_view(comment: Comment, author_name: str) -> CommentView:
        return CommentView(
            id=comment.id,
            content_id=comment.content_id,
            user_id=comment.user_id,
            parent_id=comment.parent_id,
            author_name=author_name,
            body=comment.body,
            status=comment.status,
            score=comment.score,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )
