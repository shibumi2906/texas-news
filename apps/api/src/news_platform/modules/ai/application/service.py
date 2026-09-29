from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.ai.application.ports import ProviderError, ProviderRequest
from news_platform.modules.ai.application.tasks import AITaskDefinition, ModelRouter, TaskManager
from news_platform.modules.ai.domain.models import (
    AIExecution,
    AIResult,
    PromptDefinition,
    PromptVersion,
)
from news_platform.modules.ai.domain.schemas import (
    AIAnswerMetadata,
    AIAnswerResponse,
    AIAnswerStatus,
    AIAnswerTask,
    AIQueryRequest,
    AIQuickBriefRequest,
    AISourceReference,
    GroundedAnswerOutput,
    StorySummaryOutput,
    StorySummaryResponse,
)
from news_platform.modules.ai.infrastructure.providers import (
    ProviderRegistry,
    extractive_answer,
    extractive_bullets,
)
from news_platform.modules.ai.infrastructure.repository import AIRepository
from news_platform.modules.analytics.application.service import AnalyticsIngestionService
from news_platform.modules.analytics.domain.models import BehaviorEventType
from news_platform.modules.analytics.domain.schemas import BehaviorEventCreate
from news_platform.modules.feeds.application.service import FeedService
from news_platform.modules.feeds.domain.schemas import FeedKind
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.application.service import PublicSiteService
from news_platform.modules.public_site.infrastructure.repository import PublicContentRecord
from news_platform.modules.search.application.service import SearchService
from news_platform.modules.search.domain.schemas import SearchQuery
from news_platform.modules.search.infrastructure.postgres import PostgresSearchBackend
from news_platform.modules.users.application.rate_limit import enforce_rate_limit


class AIResourceNotFoundError(Exception):
    pass


class AIConfigurationError(Exception):
    pass


class AIFeatureDisabledError(Exception):
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


def _strict_answer(raw: str) -> GroundedAnswerOutput:
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    try:
        return GroundedAnswerOutput.model_validate_json(candidate)
    except ValidationError as first_error:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start >= 0 and end > start:
            try:
                return GroundedAnswerOutput.model_validate_json(candidate[start : end + 1])
            except ValidationError:
                pass
        raise first_error


def _content_source(record: PublicContentRecord, max_tokens: int) -> dict[str, Any]:
    remaining = max(0, max_tokens * 4 - 200)

    def bounded(value: str | None) -> str | None:
        nonlocal remaining
        if value is None:
            return None
        clipped = value[:remaining]
        remaining -= len(clipped)
        return clipped

    return {
        "title": bounded(record.title),
        "subtitle": bounded(record.subtitle),
        "description": bounded(record.description),
        "body": bounded(record.body or ""),
        "language": record.language,
    }


def _content_hash(record: PublicContentRecord) -> str:
    content = record.content
    payload = {
        "id": str(content.id),
        "title": record.title,
        "subtitle": record.subtitle,
        "description": record.description,
        "body": record.body,
        "language": record.language,
        "editorial_status": content.status.value,
        "upstream_status": content.upstream_status.value,
        "site_published_at": (
            content.site_published_at.isoformat() if content.site_published_at else None
        ),
        "effective_updated_at": record.representation_updated_at.isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _retrieval_terms(question: str) -> str:
    ignored = {
        "a",
        "about",
        "an",
        "and",
        "are",
        "did",
        "do",
        "for",
        "happened",
        "how",
        "in",
        "is",
        "me",
        "of",
        "on",
        "the",
        "this",
        "today",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "week",
        "weekend",
    }
    words = re.findall(r"[\w'-]+", question.lower(), flags=re.UNICODE)
    return " ".join(word for word in words if word not in ignored)[:200]


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
        record = await public_service.repository.get_story(portal, story_slug, self.now, language)
        if record is None:
            raise AIResourceNotFoundError("story not found")

        task = await self._configured_task(portal.id, "story_summary")
        routes = ModelRouter.candidates(task)
        if not routes:
            raise AIConfigurationError("no allowed model route")
        prompt, experiment_metadata = await self._prompt_for(portal.id, task, record.content.id)
        if prompt is None:
            raise AIConfigurationError("active prompt version unavailable")
        cache_task = replace(task, prompt_version=prompt.version)

        content_hash = _content_hash(record)
        execution_lock_key = _cache_key(
            cache_task,
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
                _cache_key(cache_task, content_hash, str(portal.id), language, cached_model),
                self.now,
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
                    metadata_={"schema_version": task.response_schema, **experiment_metadata},
                )
            )
            if output is not None:
                fallback_used = route_index > 0
                break

        if output is None:
            output = StorySummaryOutput(bullets=extractive_bullets(source))
            fallback_used = True

        cache_key = _cache_key(
            cache_task,
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

    async def ai_search(
        self, portal_slug: str, payload: AIQueryRequest, redis: Any
    ) -> AIAnswerResponse:
        portal, public = await self._portal(portal_slug, payload.language, "ai_search")
        await self._limit(redis, portal, payload.anonymous_id, "search")
        terms = _retrieval_terms(payload.question)
        records: list[PublicContentRecord] = []
        if terms:
            page = await SearchService(public, PostgresSearchBackend(self.session)).page(
                portal_slug, SearchQuery(q=terms, language=payload.language, limit=5)
            )
            records = await self._records(
                portal, public, [item.slug for item in page.items], payload.language
            )
        result = await self._grounded_answer(
            "ai_search",
            portal,
            public,
            records,
            payload.question,
            AIAnswerMetadata(timezone=portal.timezone),
        )
        await self._analytics(portal_slug, payload, result, "ai_search")
        return result

    async def story_question(
        self, portal_slug: str, story_slug: str, payload: AIQueryRequest, redis: Any
    ) -> AIAnswerResponse:
        portal, public = await self._portal(portal_slug, payload.language, "ai_chat")
        await self._limit(redis, portal, payload.anonymous_id, "story_question")
        record = await public.repository.get_story(portal, story_slug, self.now, payload.language)
        if record is None:
            raise AIResourceNotFoundError("story not found")
        result = await self._grounded_answer(
            "story_question",
            portal,
            public,
            [record],
            payload.question,
            AIAnswerMetadata(timezone=portal.timezone),
        )
        await self._analytics(
            portal_slug, payload, result, "story_question", content_id=record.content.id
        )
        return result

    async def trending(
        self, portal_slug: str, payload: AIQuickBriefRequest, redis: Any
    ) -> AIAnswerResponse:
        portal, public = await self._portal(portal_slug, payload.language, "ai_chat")
        await self._limit(redis, portal, payload.anonymous_id, "trending")
        page = await FeedService(
            self.session, redis, self.settings.feed_cache_ttl_seconds, now=self.now
        ).page(
            portal_slug,
            FeedKind.TRENDING,
            language=payload.language,
            limit=5,
            cursor_value=None,
        )
        records = await self._records(
            portal, public, [item.slug for item in page.items], payload.language
        )
        result = await self._grounded_answer(
            "trending_digest",
            portal,
            public,
            records,
            "What is trending?",
            AIAnswerMetadata(timezone=portal.timezone, ranking_authoritative=True),
        )
        await self._analytics(portal_slug, payload, result, "trending")
        return result

    async def today(
        self, portal_slug: str, payload: AIQuickBriefRequest, redis: Any
    ) -> AIAnswerResponse:
        portal, public = await self._portal(portal_slug, payload.language, "ai_chat")
        await self._limit(redis, portal, payload.anonymous_id, "today")
        timezone = ZoneInfo(portal.timezone)
        local_now = self.now.astimezone(timezone)
        local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = local_start.astimezone(UTC)
        window_end = (local_start + timedelta(days=1)).astimezone(UTC)
        records = await public.repository.list_content_window(
            portal,
            self.now,
            language=payload.language,
            published_from=window_start,
            published_before=window_end,
            limit=10,
        )
        result = await self._grounded_answer(
            "today_digest",
            portal,
            public,
            records,
            "What happened today?",
            AIAnswerMetadata(
                timezone=portal.timezone, window_start=window_start, window_end=window_end
            ),
        )
        await self._analytics(portal_slug, payload, result, "today")
        return result

    async def _portal(
        self, portal_slug: str, language: str, feature: str
    ) -> tuple[Portal, PublicSiteService]:
        public = PublicSiteService(self.session, self.now)
        portal = await public.repository.get_portal(portal_slug)
        if portal is None or language not in portal.supported_languages:
            raise AIResourceNotFoundError("portal or language not found")
        if portal.feature_flags.get(feature) is False:
            raise AIFeatureDisabledError(f"{feature} is disabled")
        return portal, public

    async def _limit(self, redis: Any, portal: Portal, actor: str, surface: str) -> None:
        await enforce_rate_limit(
            redis,
            f"ai:{portal.id}:{actor}:{surface}",
            limit=self.settings.ai_rate_limit,
            window_seconds=self.settings.ai_rate_limit_window_seconds,
        )

    async def _records(
        self,
        portal: Portal,
        public: PublicSiteService,
        slugs: list[str],
        language: str,
    ) -> list[PublicContentRecord]:
        records: list[PublicContentRecord] = []
        for slug in slugs:
            record = await public.repository.get_story(portal, slug, self.now, language)
            if record is not None:
                records.append(record)
        return records

    async def _analytics(
        self,
        portal_slug: str,
        payload: AIQueryRequest | AIQuickBriefRequest,
        result: AIAnswerResponse,
        surface: str,
        content_id: UUID | None = None,
    ) -> None:
        await AnalyticsIngestionService(
            self.session,
            now=self.now,
            max_age_days=self.settings.analytics_event_max_age_days,
            future_skew_seconds=self.settings.analytics_future_skew_seconds,
        ).collect(
            portal_slug,
            BehaviorEventCreate(
                id=payload.event_id,
                anonymous_id=payload.anonymous_id,
                session_id=payload.session_id,
                event_type=BehaviorEventType.AI_QUERY,
                content_id=content_id,
                timestamp=self.now,
                properties={
                    "surface": surface,
                    "answer_status": result.status.value,
                    "source_count": len(result.sources),
                },
            ),
        )

    async def _grounded_answer(
        self,
        task_name: AIAnswerTask,
        portal: Portal,
        public: PublicSiteService,
        records: list[PublicContentRecord],
        question: str,
        metadata: AIAnswerMetadata,
    ) -> AIAnswerResponse:
        if not records:
            return AIAnswerResponse(
                task=task_name,
                answer="The platform does not have enough published information to answer that.",
                status=AIAnswerStatus.INSUFFICIENT_EVIDENCE,
                insufficient_evidence=True,
                generated=False,
                fallback_used=False,
                cached=False,
                sources=[],
                metadata=metadata,
            )

        task = await self._configured_task(portal.id, task_name)
        routes = ModelRouter.candidates(task)
        if not routes:
            raise AIConfigurationError("no allowed model route")
        prompt, experiment_metadata = await self._prompt_for(portal.id, task, records[0].content.id)
        if prompt is None:
            raise AIConfigurationError("active prompt version unavailable")
        cache_task = replace(task, prompt_version=prompt.version)

        source = self._answer_source(records, question, task.max_input_tokens)
        source_json = json.dumps(source, ensure_ascii=False, separators=(",", ":"))
        content_hash = hashlib.sha256(source_json.encode()).hexdigest()
        lock_key = _cache_key(
            cache_task,
            content_hash,
            str(portal.id),
            records[0].language,
            task.primary_model,
        )
        await self.repository.lock_cache_key(lock_key)
        for cached_model in [
            *(f"{route.provider}:{route.model}" for route in routes),
            "deterministic:extractive-v1",
        ]:
            cached = await self.repository.cached_result(
                _cache_key(
                    cache_task,
                    content_hash,
                    str(portal.id),
                    records[0].language,
                    cached_model,
                ),
                self.now,
            )
            if cached is not None:
                return self._answer_response(
                    task_name,
                    public,
                    portal,
                    records,
                    GroundedAnswerOutput.model_validate(cached.output),
                    metadata,
                    cached.fallback_used,
                    cached.provider != "deterministic",
                    True,
                )

        output: GroundedAnswerOutput | None = None
        selected_provider, selected_model = "deterministic", "extractive-v1"
        fallback_used = False
        for attempt in range(task.max_retries + 1):
            route_index = min(attempt, len(routes) - 1)
            route = routes[route_index]
            started = monotonic()
            response = None
            error_type: str | None = None
            try:
                response = await self.providers.get(route.provider).execute(
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
                    output = _strict_answer(response.output_text)
                except ValidationError as exc:
                    raise ProviderError("invalid_structured_output") from exc
                selected_provider, selected_model = route.provider, route.model
            except ProviderError as exc:
                error_type = exc.error_type
            self.session.add(
                AIExecution(
                    task=task.task_name,
                    provider=route.provider,
                    model=route.model,
                    gateway=response.gateway if response else None,
                    latency_ms=max(0, round((monotonic() - started) * 1000)),
                    input_tokens=response.input_tokens
                    if response
                    else max(1, len(source_json) // 4),
                    output_tokens=response.output_tokens if response else 0,
                    estimated_cost=response.estimated_cost if response else Decimal("0"),
                    success=output is not None,
                    error_type=error_type,
                    retry_count=attempt,
                    fallback_used=route_index > 0,
                    content_id=records[0].content.id,
                    portal_id=portal.id,
                    prompt_version=prompt.version,
                    metadata_={
                        "schema_version": task.response_schema,
                        "source_count": len(records),
                        **experiment_metadata,
                    },
                )
            )
            if output is not None:
                fallback_used = route_index > 0
                break

        if output is None:
            output = GroundedAnswerOutput(answer=extractive_answer(source))
            fallback_used = True
        cache_key = _cache_key(
            cache_task,
            content_hash,
            str(portal.id),
            records[0].language,
            f"{selected_provider}:{selected_model}",
        )
        await self.repository.remove_expired_result(cache_key, self.now)
        self.session.add(
            AIResult(
                cache_key=cache_key,
                task=task.task_name,
                content_id=records[0].content.id,
                portal_id=portal.id,
                language=records[0].language,
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
        return self._answer_response(
            task_name,
            public,
            portal,
            records,
            output,
            metadata,
            fallback_used,
            selected_provider != "deterministic",
            False,
        )

    async def _configured_task(self, portal_id: UUID, task_name: str) -> AITaskDefinition:
        task = TaskManager(self.settings).get(task_name)
        configured = await self.repository.task_config(portal_id, task_name)
        if configured is None:
            return task
        available = frozenset(
            provider.strip()
            for provider in self.settings.ai_allowed_providers.split(",")
            if provider.strip()
        )
        return replace(
            task,
            primary_model=configured.primary_model,
            fallback_models=tuple(configured.fallback_models),
            allowed_providers=frozenset(configured.allowed_providers).intersection(available),
            max_cost=configured.max_cost,
            max_input_tokens=configured.max_input_tokens,
            max_output_tokens=configured.max_output_tokens,
            max_retries=configured.max_retries,
            timeout_seconds=float(configured.timeout_seconds),
            prompt_version=configured.prompt_version,
        )

    async def _prompt_for(
        self, portal_id: UUID, task: AITaskDefinition, content_id: UUID
    ) -> tuple[PromptVersion | None, dict[str, str]]:
        experiment = await self.repository.experiment(portal_id, task.task_name)
        if experiment is not None:
            digest = hashlib.sha256(
                f"{portal_id}:{task.task_name}:{content_id}".encode()
            ).hexdigest()
            variant = "b" if int(digest[:8], 16) % 100 < experiment.variant_b_percent else "a"
            version_id = (
                experiment.prompt_version_b_id if variant == "b" else experiment.prompt_version_a_id
            )
            prompt = await self.session.scalar(
                select(PromptVersion)
                .join(PromptDefinition, PromptDefinition.id == PromptVersion.prompt_definition_id)
                .where(
                    PromptVersion.id == version_id,
                    PromptVersion.status == "active",
                    PromptDefinition.task == task.task_name,
                    PromptDefinition.portal_id == portal_id,
                )
            )
            if prompt is not None:
                return prompt, {
                    "experiment_id": str(experiment.id),
                    "experiment_variant": variant,
                }
        prompt = await self.repository.active_prompt(task.task_name, task.prompt_version, portal_id)
        if prompt is None:
            prompt = await self.repository.active_prompt(task.task_name, task.prompt_version)
        return prompt, {}

    @staticmethod
    def _answer_source(
        records: list[PublicContentRecord], question: str, max_tokens: int
    ) -> dict[str, Any]:
        remaining = max(0, max_tokens * 4 - len(question) - 300)
        items: list[dict[str, Any]] = []
        per_item = max(200, remaining // len(records))
        for record in records:
            item = {
                "id": str(record.content.id),
                "title": record.title,
                "subtitle": record.subtitle,
                "description": record.description,
                "body": (record.body or "")[:per_item],
                "published_at": record.content.site_published_at.isoformat()
                if record.content.site_published_at
                else None,
            }
            items.append(item)
        return {"question": question, "items": items}

    @staticmethod
    def _answer_response(
        task_name: AIAnswerTask,
        public: PublicSiteService,
        portal: Portal,
        records: list[PublicContentRecord],
        output: GroundedAnswerOutput,
        metadata: AIAnswerMetadata,
        fallback_used: bool,
        generated: bool,
        cached: bool,
    ) -> AIAnswerResponse:
        sources = [public.story_summary(portal, record) for record in records]
        return AIAnswerResponse(
            task=task_name,
            answer=output.answer,
            status=AIAnswerStatus.ANSWERED,
            insufficient_evidence=False,
            generated=generated,
            fallback_used=fallback_used,
            cached=cached,
            sources=[
                AISourceReference(
                    content_id=source.id,
                    title=source.title,
                    url=source.url,
                    canonical_url=source.canonical_url,
                )
                for source in sources
            ],
            metadata=metadata,
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
            language=record.language,
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
