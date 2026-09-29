from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AITaskName = Literal[
    "story_summary",
    "ai_search",
    "story_question",
    "trending_digest",
    "today_digest",
]


class AITaskConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_model: str = Field(min_length=3, max_length=255, pattern=r"^[a-z0-9_-]+:[^\s:][^\s]*$")
    fallback_models: list[str] = Field(default_factory=list, max_length=5)
    allowed_providers: list[str] = Field(min_length=1, max_length=8)
    max_cost: Decimal = Field(ge=0, le=100, max_digits=12, decimal_places=6)
    max_input_tokens: int = Field(ge=128, le=100000)
    max_output_tokens: int = Field(ge=32, le=10000)
    max_retries: int = Field(ge=0, le=5)
    timeout_seconds: float = Field(gt=0, le=120)
    prompt_version: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_routes(self) -> AITaskConfigUpdate:
        if len(set(self.allowed_providers)) != len(self.allowed_providers):
            raise ValueError("allowed_providers must be unique")
        if len(set(self.fallback_models)) != len(self.fallback_models):
            raise ValueError("fallback_models must be unique")
        if self.primary_model in self.fallback_models:
            raise ValueError("primary_model cannot also be a fallback")
        for route in [self.primary_model, *self.fallback_models]:
            provider, separator, model = route.partition(":")
            if not separator or not provider or not model or provider not in self.allowed_providers:
                raise ValueError("every route must use an allowed provider and model")
        return self


class PromptVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template: str = Field(min_length=20, max_length=12000)
    notes: str | None = Field(default=None, max_length=1000)


class ExperimentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    prompt_version_a_id: UUID
    prompt_version_b_id: UUID
    variant_b_percent: int = Field(ge=1, le=99)
    status: Literal["running", "paused"]

    @model_validator(mode="after")
    def require_two_variants(self) -> ExperimentUpdate:
        if self.prompt_version_a_id == self.prompt_version_b_id:
            raise ValueError("A/B test requires two distinct prompt versions")
        return self


class PromptVersionView(BaseModel):
    id: UUID
    version: int
    status: str
    template: str
    notes: str | None
    created_at: datetime
    created_by: str
    scope: Literal["portal", "system"]


class AITaskAdminView(BaseModel):
    task: AITaskName
    primary_model: str
    fallback_models: list[str]
    allowed_providers: list[str]
    max_cost: Decimal
    max_input_tokens: int
    max_output_tokens: int
    max_retries: int
    timeout_seconds: float
    prompt_version: int
    is_portal_override: bool
    prompts: list[PromptVersionView]


class AIExperimentView(BaseModel):
    id: UUID | None
    task: AITaskName
    name: str | None
    prompt_version_a_id: UUID | None
    prompt_version_b_id: UUID | None
    variant_b_percent: int | None
    status: str


class AIAdminOverview(BaseModel):
    portal_slug: str
    available_providers: list[str]
    provider_credentials: dict[str, bool]
    tasks: list[AITaskAdminView]
    experiments: list[AIExperimentView]
    usage: dict[str, int | float | str]
    models: list[dict[str, int | float | str | None]]
    errors: list[dict[str, int | str | None]]
