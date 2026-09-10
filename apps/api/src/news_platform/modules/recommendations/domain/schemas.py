from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from news_platform.modules.recommendations.domain.models import PersonalizationTargetType


class UserInterestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_type: PersonalizationTargetType
    target_id: UUID
    weight: int = Field(default=3, ge=1, le=5)


class UserInterestsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[UserInterestInput] = Field(max_length=100)


class UserInterestView(UserInterestInput):
    pass


class UserInterestsView(BaseModel):
    items: list[UserInterestView]


class InterestOption(BaseModel):
    target_type: PersonalizationTargetType
    target_id: UUID
    name: str


class InterestCatalog(BaseModel):
    items: list[InterestOption]


class AffinityBatchResult(BaseModel):
    processed: int
    applied: int
