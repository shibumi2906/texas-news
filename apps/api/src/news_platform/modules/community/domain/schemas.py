from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from news_platform.modules.community.domain.models import (
    CommentStatus,
    FollowTargetType,
    ReactionType,
)


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    body: str = Field(min_length=1, max_length=4000)
    parent_id: UUID | None = None


class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=4000)


class CommentView(BaseModel):
    id: UUID
    content_id: UUID
    user_id: UUID
    parent_id: UUID | None
    author_name: str
    body: str
    status: CommentStatus
    score: int
    created_at: datetime
    updated_at: datetime


class CommentPage(BaseModel):
    items: list[CommentView]
    next_cursor: str | None


class ReactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reaction_type: ReactionType


class ToggleView(BaseModel):
    active: bool
    status: Literal["created", "updated", "unchanged", "removed"]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["spam", "abuse", "harassment", "misinformation", "other"]
    details: str | None = Field(default=None, max_length=500)


class ReportView(BaseModel):
    id: UUID
    status: Literal["created", "duplicate"]


class ModerationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CommentStatus


class FollowView(BaseModel):
    target_type: FollowTargetType
    target_id: UUID
    created_at: datetime


class SaveView(BaseModel):
    content_id: UUID
    created_at: datetime
