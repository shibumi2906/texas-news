from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin


class CommentStatus(StrEnum):
    VISIBLE = "visible"
    PENDING = "pending"
    HIDDEN = "hidden"
    REMOVED = "removed"
    SPAM = "spam"
    BLOCKED = "blocked"


class ReactionType(StrEnum):
    LIKE = "like"
    LOVE = "love"
    LAUGH = "laugh"
    WOW = "wow"
    SAD = "sad"
    ANGRY = "angry"


class FollowTargetType(StrEnum):
    ENTITY = "entity"
    GEOGRAPHY = "geography"
    TOPIC = "topic"


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('visible', 'pending', 'hidden', 'removed', 'spam', 'blocked')",
            name="status",
        ),
        CheckConstraint("char_length(body) BETWEEN 1 AND 4000", name="body_length"),
        Index("ix_comments_story_order", "portal_id", "content_id", "created_at", "id"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=CommentStatus.VISIBLE, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Reaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reactions"
    __table_args__ = (
        CheckConstraint(
            "reaction_type IN ('like', 'love', 'laugh', 'wow', 'sad', 'angry')", name="type"
        ),
        CheckConstraint("(content_id IS NULL) <> (comment_id IS NULL)", name="one_target"),
        UniqueConstraint("portal_id", "user_id", "content_id", name="uq_reactions_user_content"),
        UniqueConstraint("portal_id", "user_id", "comment_id", name="uq_reactions_user_comment"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE")
    )
    comment_id: Mapped[UUID | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"))
    reaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CommentReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "comment_reports"
    __table_args__ = (
        UniqueConstraint(
            "portal_id", "user_id", "comment_id", name="uq_comment_reports_user_comment"
        ),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    comment_id: Mapped[UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Save(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "saves"
    __table_args__ = (
        UniqueConstraint("portal_id", "user_id", "content_id", name="uq_saves_user_content"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Follow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "follows"
    __table_args__ = (
        CheckConstraint("target_type IN ('entity', 'geography', 'topic')", name="target_type"),
        UniqueConstraint(
            "portal_id", "user_id", "target_type", "target_id", name="uq_follows_user_target"
        ),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModerationAuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "moderation_audit_logs"

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    moderator_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    comment_id: Mapped[UUID] = mapped_column(
        ForeignKey("comments.id", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
