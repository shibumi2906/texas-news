from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.ai.application.ports import ProviderError, ProviderRequest
from news_platform.modules.ai.application.tasks import AITaskDefinition, ModelRouter, TaskManager
from news_platform.modules.ai.domain.models import AIExecution, AIResult
from news_platform.modules.ai.domain.schemas import (
    AISourceReference,
    StorySummaryOutput,
    StorySummaryResponse,
)
from news_platform.modules.ai.infrastructure.providers import ProviderRegistry, extractive_bullets
from news_platform.modules.ai.infrastructure.repository import AIRepository
from news_platform.modules.public_site.application.service import PublicSiteService
from news_platform.modules.public_site.infrastructure.repository import PublicContentRecord


class AIResourceNotFoundError(Exception):
    pass


class AIConfigurationError(Exception):
    pass


def _strict_output(raw: str) -> StorySummaryOutput:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    try:
        return StorySummaryOutput.model_validate_json(candidate)
    except ValidationError as first_error:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return StorySummaryOutput.model_validate_json(candidate[start : end + 1])
            except ValidationError:
                pass
        raise first_error


def _content_source(record: PublicContentRecord, max_tokens: int) -> dict[str, Any]:
    content = record.content
    remaining = max(0, max_tokens * 4 - 200)

    def bounded(value: str | None) -> str | None:
        nonlocal remaining
        if value is None:
            return None
        clipped = value[:remaining]
        remaining -= len(clipped)
        return clipped

    return {
        "title": bounded(content.title),
        "subtitle": bounded(content.subtitle),
        "description": bounded(content.description),
        "body": bounded(content.body or ""),
        "language": content.primary_language,
    }


def _content_hash(record: PublicContentRecord) -> str:
    content = record.content
    payload = {
        "id": str(content.id),
        "title": content.title,
        "subtitle": content.subtitle,
        "description": content.description,
        "body": content.body,
        "language": content.primary_language,
        "editorial_status": content.status.value,
        "upstream_status": content.upstream_status.value,
        "site_published_at": (
            content.site_published_at.isoformat() if content.site_published_at else None
        ),
        "effective_updated_at": content.updated_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _cache_key(
    task: AITaskDefinition, content_hash: str, portal_id: str, language: str, model: str
) -> str:
    raw = "|".join(
        (
            content_hash,
            task.task_name,
            model,
            str(task.prompt_version),
            language,
            task.response_schema,
            portal_id,
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class AIService:
    def __init__(
        self,
        session: AsyncSession,
        providers: ProviderRegistry,
        settings: Settings,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.providers = providers
        self.settings = settings
        self.now = now or datetime.now(UTC)
        self.repository = AIRepository(session)

    async def story_summary(
        self, portal_slug: str, story_slug: str, language: str
    ) -> StorySummaryResponse:
        public_service = PublicSiteService(self.session, self.now)
        portal = await public_service.repository.get_portal(portal_slug)
        if portal is None or language not in portal.supported_languages:
            raise AIResourceNotFoundError("story not found")
        record = await public_service.repository.get_story(portal, story_slug, self.now)
        if record is None or record.content.primary_language != language:
            raise AIResourceNotFoundError("story not found")

        task = TaskManager(self.settings).get("story_summary")
        routes = ModelRouter.candidates(task)
        if not routes:
            raise AIConfigurationError("no allowed model route")
        prompt = await self.repository.active_prompt(task.task_name, task.prompt_version)
        if prompt is None:
            raise AIConfigurationError("active prompt version unavailable")

        content_hash = _content_hash(record)
        execution_lock_key = _cache_key(
            task,
            content_hash,
            str(portal.id),
            language,
            self.settings.ai_story_summary_primary_model,
        )
        await self.repository.lock_cache_key(execution_lock_key)
        cached_models = [f"{route.provider}:{route.model}" for route in routes]
        cached_models.append("deterministic:extractive-v1")
        for cached_model in cached_models:
            cached = await self.repository.cached_result(
                _cache_key(task, content_hash, str(portal.id), language, cached_model), self.now
            )
            if cached is not None:
                cached_output = StorySummaryOutput.model_validate(cached.output)
                return self._response(
                    public_service,
                    portal,
                    record,
                    cached_output,
                    cached.fallback_used,
                    cached.provider != "deterministic",
                    True,
                )

        source = _content_source(record, task.max_input_tokens)
        source_json = json.dumps(source, ensure_ascii=False, separators=(",", ":"))
        output: StorySummaryOutput | None = None
        selected_provider = "deterministic"
        selected_model = "extractive-v1"
        fallback_used = False
        max_attempts = task.max_retries + 1

        for attempt in range(max_attempts):
            route_index = min(attempt, len(routes) - 1)
            route = routes[route_index]
            started = monotonic()
            error_type: str | None = None
            response = None
            try:
                adapter = self.providers.get(route.provider)
                response = await adapter.execute(
                    ProviderRequest(
                        task=task.task_name,
                        model=route.model,
                        system_prompt=prompt.template,
                        source_json=source_json,
                        max_output_tokens=task.max_output_tokens,
                        timeout_seconds=task.timeout_seconds,
                        reasoning_level=task.reasoning_level,
                    )
                )
                if response.estimated_cost > task.max_cost:
                    raise ProviderError("cost_limit")
                if response.output_tokens > task.max_output_tokens:
                    raise ProviderError("output_token_limit")
                try:
                    output = _strict_output(response.output_text)
                except ValidationError as exc:
                    raise ProviderError("invalid_structured_output") from exc
                selected_provider = route.provider
                selected_model = route.model
            except ProviderError as exc:
                error_type = exc.error_type

            latency_ms = max(0, round((monotonic() - started) * 1000))
            self.session.add(
                AIExecution(
                    task=task.task_name,
                    provider=route.provider,
                    model=route.model,
                    gateway=response.gateway if response else None,
                    latency_ms=latency_ms,
                    input_tokens=response.input_tokens
                    if response
                    else max(1, len(source_json) // 4),
                    output_tokens=response.output_tokens if response else 0,
                    estimated_cost=response.estimated_cost if response else Decimal("0"),
                    success=output is not None,
                    error_type=error_type,
                    retry_count=attempt,
                    fallback_used=route_index > 0,
                    content_id=record.content.id,
                    portal_id=portal.id,
                    prompt_version=prompt.version,
                    metadata_={"schema_version": task.response_schema},
                )
            )
            if output is not None:
                fallback_used = route_index > 0
                break

        if output is None:
            output = StorySummaryOutput(bullets=extractive_bullets(source))
            fallback_used = True

        cache_key = _cache_key(
            task,
            content_hash,
            str(portal.id),
            language,
            f"{selected_provider}:{selected_model}",
        )
        await self.repository.remove_expired_result(cache_key, self.now)

        self.session.add(
            AIResult(
                cache_key=cache_key,
                task=task.task_name,
                content_id=record.content.id,
                portal_id=portal.id,
                language=language,
                content_hash=content_hash,
                provider=selected_provider,
                model=selected_model,
                prompt_version=prompt.version,
                schema_version=task.response_schema,
                output=output.model_dump(mode="json"),
                fallback_used=fallback_used,
                expires_at=self.now + timedelta(seconds=task.cache_ttl_seconds),
            )
        )
        return self._response(
            public_service,
            portal,
            record,
            output,
            fallback_used,
            selected_provider != "deterministic",
            False,
        )

    @staticmethod
    def _response(
        public_service: PublicSiteService,
        portal: Any,
        record: PublicContentRecord,
        output: StorySummaryOutput,
        fallback_used: bool,
        provider_generated: bool,
        cached: bool,
    ) -> StorySummaryResponse:
        story = public_service.story_summary(portal, record)
        return StorySummaryResponse(
            language=record.content.primary_language,
            bullets=output.bullets,
            generated=provider_generated,
            fallback_used=fallback_used,
            cached=cached,
            sources=[
                AISourceReference(
                    content_id=story.id,
                    title=story.title,
                    url=story.url,
                    canonical_url=story.canonical_url,
                )
            ],
        )
