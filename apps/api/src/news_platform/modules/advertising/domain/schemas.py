from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlacementWrite(StrictModel):
    code: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=160)
    allowed_content_types: list[
        Literal["article", "image", "gallery", "meme", "video", "short", "live", "event"]
    ] = Field(default_factory=list, max_length=8)
    active: bool = True


class PlacementView(PlacementWrite):
    id: UUID


class CreativeWrite(StrictModel):
    name: str = Field(min_length=2, max_length=160)
    format: Literal["image", "html", "text"]
    asset_url: HttpUrl | None = None
    click_url: HttpUrl
    alt_text: str = Field(min_length=1, max_length=300)
    active: bool = True

    @model_validator(mode="after")
    def validate_asset(self) -> CreativeWrite:
        if self.format == "image" and self.asset_url is None:
            raise ValueError("image creatives require asset_url")
        return self


class CreativeView(StrictModel):
    id: UUID
    name: str
    format: str
    asset_url: str | None
    click_url: str
    alt_text: str
    active: bool


class TargetingWrite(StrictModel):
    placement_codes: list[str] = Field(default_factory=list, max_length=50)
    geography_ids: list[UUID] = Field(default_factory=list, max_length=100)
    languages: list[str] = Field(default_factory=list, max_length=20)
    category_ids: list[UUID] = Field(default_factory=list, max_length=100)
    content_types: list[
        Literal["article", "image", "gallery", "meme", "video", "short", "live", "event"]
    ] = Field(default_factory=list, max_length=8)


class CampaignWrite(StrictModel):
    name: str = Field(min_length=2, max_length=180)
    status: Literal["draft", "active", "paused", "ended"] = "draft"
    priority: int = Field(default=0, ge=0, le=1000)
    starts_at: datetime
    ends_at: datetime | None = None
    targeting: TargetingWrite
    creatives: list[CreativeWrite] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_dates(self) -> CampaignWrite:
        if self.starts_at.tzinfo is None or self.starts_at.utcoffset() is None:
            raise ValueError("starts_at must be timezone-aware")
        if self.ends_at is not None:
            if self.ends_at.tzinfo is None or self.ends_at.utcoffset() is None:
                raise ValueError("ends_at must be timezone-aware")
            if self.ends_at <= self.starts_at:
                raise ValueError("ends_at must be after starts_at")
        return self


class TargetingView(StrictModel):
    placement_codes: list[str]
    geography_ids: list[UUID]
    languages: list[str]
    category_ids: list[UUID]
    content_types: list[str]


class CampaignView(StrictModel):
    id: UUID
    name: str
    status: str
    priority: int
    starts_at: datetime
    ends_at: datetime | None
    targeting: TargetingView
    creatives: list[CreativeView]


class AdvertisingOverview(StrictModel):
    portal_slug: str
    enabled: bool
    placements: list[PlacementView]
    campaigns: list[CampaignView]
    impressions: int
    clicks: int


class AdDecision(StrictModel):
    placement_id: UUID
    campaign_id: UUID
    creative_id: UUID
    format: str
    asset_url: str | None
    click_url: str
    alt_text: str


class ImpressionCreate(StrictModel):
    id: UUID
    placement_id: UUID
    campaign_id: UUID
    creative_id: UUID
    content_id: UUID | None = None
    occurred_at: datetime


class ClickCreate(StrictModel):
    id: UUID
    impression_id: UUID
    occurred_at: datetime


class TrackingReceipt(StrictModel):
    id: UUID
    status: Literal["accepted", "duplicate"]
