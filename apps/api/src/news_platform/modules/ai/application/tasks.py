from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from news_platform.core.config import Settings


@dataclass(frozen=True)
class AITaskDefinition:
    task_name: str
    primary_model: str
    fallback_models: tuple[str, ...]
    allowed_providers: frozenset[str]
    max_cost: Decimal
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: float
    max_retries: int
    reasoning_level: str
    response_schema: str
    prompt_version: int
    cache_ttl_seconds: int


class TaskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get(self, task_name: str) -> AITaskDefinition:
        if task_name not in {
            "story_summary",
            "ai_search",
            "story_question",
            "trending_digest",
            "today_digest",
        }:
            raise KeyError(task_name)
        is_summary = task_name == "story_summary"
        fallbacks = tuple(
            model.strip()
            for model in (
                self.settings.ai_story_summary_fallback_models
                if is_summary
                else self.settings.ai_query_fallback_models
            ).split(",")
            if model.strip()
        )
        providers = frozenset(
            provider.strip()
            for provider in self.settings.ai_allowed_providers.split(",")
            if provider.strip()
        )
        return AITaskDefinition(
            task_name=task_name,
            primary_model=(
                self.settings.ai_story_summary_primary_model
                if is_summary
                else self.settings.ai_query_primary_model
            ),
            fallback_models=fallbacks,
            allowed_providers=providers,
            max_cost=Decimal(
                str(
                    self.settings.ai_story_summary_max_cost
                    if is_summary
                    else self.settings.ai_query_max_cost
                )
            ),
            max_input_tokens=(
                self.settings.ai_story_summary_max_input_tokens
                if is_summary
                else self.settings.ai_query_max_input_tokens
            ),
            max_output_tokens=(
                self.settings.ai_story_summary_max_output_tokens
                if is_summary
                else self.settings.ai_query_max_output_tokens
            ),
            timeout_seconds=self.settings.ai_provider_timeout_seconds,
            max_retries=(
                self.settings.ai_story_summary_max_retries
                if is_summary
                else self.settings.ai_query_max_retries
            ),
            reasoning_level="none",
            response_schema="story_summary.v1" if is_summary else "grounded_answer.v1",
            prompt_version=1,
            cache_ttl_seconds=self.settings.ai_cache_ttl_seconds,
        )


@dataclass(frozen=True)
class ModelRoute:
    provider: str
    model: str


class ModelRouter:
    @staticmethod
    def candidates(task: AITaskDefinition) -> tuple[ModelRoute, ...]:
        routes: list[ModelRoute] = []
        for configured in (task.primary_model, *task.fallback_models):
            provider, separator, model = configured.partition(":")
            if not separator or not provider or not model:
                continue
            if provider not in task.allowed_providers:
                continue
            route = ModelRoute(provider=provider, model=model)
            if route not in routes:
                routes.append(route)
        return tuple(routes)
