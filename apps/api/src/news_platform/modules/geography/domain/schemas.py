from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from news_platform.modules.geography.domain.models import GeographyType


class GeographyNodeCreate(BaseModel):
    type: GeographyType
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    parent_id: UUID | None = None
    timezone: str | None = Field(default=None, max_length=64)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str | None) -> str | None:
        return value.upper() if value else None
