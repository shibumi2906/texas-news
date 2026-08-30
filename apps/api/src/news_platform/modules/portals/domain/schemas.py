from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from news_platform.modules.portals.domain.models import PortalStatus

LANGUAGE_PATTERN = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class PortalCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=255)
    status: PortalStatus = PortalStatus.DRAFT
    primary_geography_id: UUID | None = None
    default_language: str = "en"
    supported_languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1)
    timezone: str = Field(min_length=1, max_length=64)
    branding: dict[str, Any] = Field(default_factory=dict)
    logo: str | None = None
    category_settings: dict[str, Any] = Field(default_factory=dict)
    ranking_settings: dict[str, Any] = Field(default_factory=dict)
    ai_settings: dict[str, Any] = Field(default_factory=dict)
    advertising_settings: dict[str, Any] = Field(default_factory=dict)
    seo_settings: dict[str, Any] = Field(default_factory=dict)
    feature_flags: dict[str, Any] = Field(default_factory=dict)

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "." not in normalized or " " in normalized:
            raise ValueError("domain must be a valid hostname")
        return normalized

    @field_validator("default_language")
    @classmethod
    def validate_default_language(cls, value: str) -> str:
        if not LANGUAGE_PATTERN.fullmatch(value):
            raise ValueError("invalid language code")
        return value.lower()

    @field_validator("supported_languages")
    @classmethod
    def validate_supported_languages(cls, values: list[str]) -> list[str]:
        normalized = [value.lower() for value in values]
        if any(not LANGUAGE_PATTERN.fullmatch(value) for value in normalized):
            raise ValueError("invalid language code")
        if len(normalized) != len(set(normalized)):
            raise ValueError("supported languages must be unique")
        return normalized
