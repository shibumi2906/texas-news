from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from news_platform.modules.content.domain.models import ContentStatus, ContentType


class EditorialCommand(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ScheduleCommand(EditorialCommand):
    scheduled_at: datetime

    @model_validator(mode="after")
    def require_timezone(self) -> ScheduleCommand:
        if self.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must include a timezone")
        return self


class EditorialEdit(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    subtitle: str | None = Field(default=None, max_length=500)
    description: str | None = None
    body: str | None = None
    reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def require_change(self) -> EditorialEdit:
        if not self.model_fields_set.difference({"reason"}):
            raise ValueError("at least one editable field is required")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title must not be null")
        return self


class ContentAdminView(BaseModel):
    id: UUID
    external_id: str | None
    content_type: ContentType
    status: ContentStatus
    upstream_status: ContentStatus
    title: str
    scheduled_at: datetime | None
    site_published_at: datetime | None
    has_editorial_override: bool

    model_config = {"from_attributes": True}


class ContentAdminPage(BaseModel):
    items: list[ContentAdminView]
    total: int
    offset: int
    limit: int
