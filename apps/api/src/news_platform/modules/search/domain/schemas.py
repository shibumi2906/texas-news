from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from news_platform.modules.public_site.domain.schemas import PublicPortal, PublicStorySummary


class SearchQuery(BaseModel):
    q: str = Field(default="", max_length=200)
    entity: str = Field(default="", max_length=180)
    category: str = Field(default="", max_length=180)
    geography: str = Field(default="", max_length=180)
    date_from: date | None = None
    date_to: date | None = None
    language: str = Field(min_length=2, max_length=35)
    limit: int = Field(default=20, ge=1, le=50)
    cursor: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_query(self) -> SearchQuery:
        if any(ord(c) < 32 and not c.isspace() for c in self.q + self.entity):
            raise ValueError("query contains control characters")
        self.q = " ".join(self.q.split())
        self.entity = " ".join(self.entity.split())
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not follow date_to")
        if self.date_to == date.max:
            raise ValueError("date_to exceeds supported range")
        return self

    def context(self, portal_id: UUID) -> str:
        data = self.model_dump_json(exclude={"cursor", "limit"})
        return hashlib.sha256(f"{portal_id}:{data}".encode()).hexdigest()


class InvalidSearchCursorError(Exception):
    pass


class SearchCursor(BaseModel):
    version: Literal[1] = 1
    context: str
    generation: int = Field(ge=0)
    snapshot_at: AwareDatetime
    published_at: AwareDatetime
    content_id: UUID
    score: Decimal = Field(ge=0, allow_inf_nan=False)

    def encode(self) -> str:
        return base64.urlsafe_b64encode(self.model_dump_json().encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, value: str, context: str, generation: int, now: datetime) -> SearchCursor:
        try:
            cursor = cls.model_validate_json(
                base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
            )
            if (
                cursor.context != context
                or cursor.generation != generation
                or cursor.snapshot_at > now
                or cursor.published_at > cursor.snapshot_at
            ):
                raise ValueError("context or generation changed")
            return cursor
        except (ValueError, binascii.Error) as exc:
            raise InvalidSearchCursorError(
                "Search changed or cursor is invalid; restart search"
            ) from exc


class SearchPage(BaseModel):
    portal: PublicPortal
    language: str
    query: str
    items: list[PublicStorySummary]
    next_cursor: str | None
