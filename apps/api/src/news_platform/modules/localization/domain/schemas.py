from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from news_platform.modules.localization.domain.models import TranslationStatus


class TranslationCreate(BaseModel):
    portal_id: UUID
    content_item_id: UUID
    language: str = Field(min_length=2, max_length=35)
    title: str = Field(min_length=1, max_length=500)
    subtitle: str | None = Field(default=None, max_length=500)
    description: str | None = None
    body: str | None = None
    translation_source: str = Field(min_length=1, max_length=120)
    status: TranslationStatus
    reviewed_by: UUID | None = None
    source_updated_at: datetime
