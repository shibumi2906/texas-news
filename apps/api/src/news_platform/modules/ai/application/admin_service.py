from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.core.config import Settings
from news_platform.modules.ai.application.tasks import TaskManager
from news_platform.modules.ai.domain.admin_schemas import (
    AIAdminOverview,
    AIExperimentView,
    AITaskAdminView,
    AITaskConfigUpdate,
    AITaskName,
    ExperimentUpdate,
    PromptVersionCreate,
    PromptVersionView,
)
from news_platform.modules.ai.domain.models import (
    AIExecution,
    AIExperiment,
    AITaskConfig,
    PromptDefinition,
    PromptVersion,
)
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.portals.domain.models import Portal

TASKS: tuple[AITaskName, ...] = (
    "story_summary",
    "ai_search",
    "story_question",
    "trending_digest",
    "today_digest",
)


class AIAdminNotFoundError(Exception):
    pass


class AIAdminValidationError(Exception):
    pass


class AIAdminService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def overview(self, portal_slug: str) -> AIAdminOverview:
        portal = await self._portal(portal_slug)
        env_allowed = {
            value.strip()
            for value in self.settings.ai_allowed_providers.split(",")
            if value.strip()
        }
        configured_providers = sorted(
            provider
            for provider in env_allowed
            if provider == "local"
            or (
                provider == "gateway"
                and self.settings.ai_gateway_url
                and self.settings.ai_gateway_api_key
            )
        )
        task_views: list[AITaskAdminView] = []
        for task_name in TASKS:
            defaults = TaskManager(self.settings).get(task_name)
            config = await self.session.scalar(
                select(AITaskConfig).where(
                    AITaskConfig.portal_id == portal.id,
                    AITaskConfig.task == task_name,
                )
            )
            definitions = list(
                (
                    await self.session.scalars(
                        select(PromptDefinition)
                        .where(
                            PromptDefinition.task == task_name,
                            or_(
                                PromptDefinition.portal_id == portal.id,
                                PromptDefinition.portal_id.is_(None),
                            ),
                        )
                        .order_by(PromptDefinition.portal_id.is_(None), PromptDefinition.created_at)
                    )
                ).all()
            )
            prompts: list[PromptVersionView] = []
            for definition in definitions:
                versions = (
                    await self.session.scalars(
                        select(PromptVersion)
                        .where(PromptVersion.prompt_definition_id == definition.id)
                        .order_by(PromptVersion.version.desc())
                    )
                ).all()
                prompts.extend(
                    PromptVersionView(
                        id=version.id,
                        version=version.version,
                        status=version.status,
                        template=version.template,
                        notes=version.notes,
                        created_at=version.created_at,
                        created_by=version.created_by,
                        scope="portal" if definition.portal_id == portal.id else "system",
                    )
                    for version in versions
                )
            task_views.append(
                AITaskAdminView(
                    task=task_name,
                    primary_model=config.primary_model if config else defaults.primary_model,
                    fallback_models=config.fallback_models
                    if config
                    else list(defaults.fallback_models),
                    allowed_providers=(
                        [item for item in config.allowed_providers if item in configured_providers]
                        if config
                        else [
                            item
                            for item in sorted(defaults.allowed_providers)
                            if item in configured_providers
                        ]
                    ),
                    max_cost=config.max_cost if config else defaults.max_cost,
                    max_input_tokens=(
                        config.max_input_tokens if config else defaults.max_input_tokens
                    ),
                    max_output_tokens=(
                        config.max_output_tokens if config else defaults.max_output_tokens
                    ),
                    max_retries=config.max_retries if config else defaults.max_retries,
                    timeout_seconds=(
                        float(config.timeout_seconds) if config else defaults.timeout_seconds
                    ),
                    prompt_version=config.prompt_version if config else defaults.prompt_version,
                    is_portal_override=config is not None,
                    prompts=prompts,
                )
            )

        experiments = (
            await self.session.scalars(
                select(AIExperiment)
                .where(AIExperiment.portal_id == portal.id)
                .order_by(AIExperiment.task)
            )
        ).all()
        cutoff = datetime.now(UTC) - timedelta(days=30)
        usage_row = (
            await self.session.execute(
                select(
                    func.count(AIExecution.id),
                    func.coalesce(func.sum(AIExecution.input_tokens), 0),
                    func.coalesce(func.sum(AIExecution.output_tokens), 0),
                    func.coalesce(func.sum(AIExecution.estimated_cost), 0),
                    func.coalesce(func.avg(AIExecution.latency_ms), 0),
                    func.coalesce(func.sum(case((AIExecution.success.is_(False), 1), else_=0)), 0),
                ).where(AIExecution.portal_id == portal.id, AIExecution.created_at >= cutoff)
            )
        ).one()
        model_rows = (
            await self.session.execute(
                select(
                    AIExecution.provider,
                    AIExecution.model,
                    func.count(AIExecution.id),
                    func.coalesce(func.sum(AIExecution.estimated_cost), 0),
                    func.coalesce(func.avg(AIExecution.latency_ms), 0),
                    func.coalesce(func.sum(case((AIExecution.success.is_(False), 1), else_=0)), 0),
                )
                .where(AIExecution.portal_id == portal.id, AIExecution.created_at >= cutoff)
                .group_by(AIExecution.provider, AIExecution.model)
                .order_by(func.count(AIExecution.id).desc())
                .limit(50)
            )
        ).all()
        error_rows = (
            await self.session.execute(
                select(
                    AIExecution.task,
                    AIExecution.error_type,
                    func.count(AIExecution.id),
                )
                .where(
                    AIExecution.portal_id == portal.id,
                    AIExecution.created_at >= cutoff,
                    AIExecution.success.is_(False),
                )
                .group_by(AIExecution.task, AIExecution.error_type)
                .order_by(func.count(AIExecution.id).desc())
                .limit(30)
            )
        ).all()
        return AIAdminOverview(
            portal_slug=portal.slug,
            available_providers=configured_providers,
            provider_credentials={
                "gateway": bool(self.settings.ai_gateway_url and self.settings.ai_gateway_api_key)
            },
            tasks=task_views,
            experiments=[
                AIExperimentView(
                    id=item.id,
                    task=item.task,
                    name=item.name,
                    prompt_version_a_id=item.prompt_version_a_id,
                    prompt_version_b_id=item.prompt_version_b_id,
                    variant_b_percent=item.variant_b_percent,
                    status=item.status,
                )
                for item in experiments
            ],
            usage={
                "window_days": 30,
                "executions": int(usage_row[0]),
                "input_tokens": int(usage_row[1]),
                "output_tokens": int(usage_row[2]),
                "estimated_cost": str(Decimal(usage_row[3])),
                "average_latency_ms": float(usage_row[4]),
                "errors": int(usage_row[5]),
            },
            models=[
                {
                    "provider": row[0],
                    "model": row[1],
                    "executions": int(row[2]),
                    "estimated_cost": str(Decimal(row[3])),
                    "average_latency_ms": float(row[4]),
                    "errors": int(row[5]),
                }
                for row in model_rows
            ],
            errors=[
                {"task": row[0], "error_type": row[1], "count": int(row[2])} for row in error_rows
            ],
        )

    async def update_task(
        self,
        portal_slug: str,
        task: str,
        payload: AITaskConfigUpdate,
        actor: str,
    ) -> None:
        portal = await self._portal(portal_slug)
        if task not in TASKS:
            raise AIAdminNotFoundError("AI task not found")
        env_allowed = {
            value.strip()
            for value in self.settings.ai_allowed_providers.split(",")
            if value.strip()
        }
        available = {
            provider
            for provider in env_allowed
            if provider == "local"
            or (
                provider == "gateway"
                and self.settings.ai_gateway_url
                and self.settings.ai_gateway_api_key
            )
        }
        if not set(payload.allowed_providers).issubset(available):
            raise AIAdminValidationError("provider is not enabled by server configuration")
        for route in [payload.primary_model, *payload.fallback_models]:
            provider = route.partition(":")[0]
            if provider not in payload.allowed_providers:
                raise AIAdminValidationError("route provider must be allowed for this task")
        definition = await self._portal_prompt_definition(portal.id, task, create=False)
        if definition is None:
            definition = await self.session.scalar(
                select(PromptDefinition).where(
                    PromptDefinition.task == task,
                    PromptDefinition.portal_id.is_(None),
                )
            )
        if definition is None:
            raise AIAdminValidationError("prompt definition not found for this task")
        active_version = await self.session.scalar(
            select(PromptVersion.id).where(
                PromptVersion.prompt_definition_id == definition.id,
                PromptVersion.version == payload.prompt_version,
                PromptVersion.status == "active",
            )
        )
        if active_version is None:
            raise AIAdminValidationError("selected prompt version is not active for this task")
        config = await self.session.scalar(
            select(AITaskConfig).where(
                AITaskConfig.portal_id == portal.id, AITaskConfig.task == task
            )
        )
        before = self._task_snapshot(config)
        if config is None:
            config = AITaskConfig(
                portal_id=portal.id, task=task, updated_by=actor, **payload.model_dump()
            )
            self.session.add(config)
        else:
            for key, value in payload.model_dump().items():
                setattr(config, key, value)
            config.updated_by = actor
        await self.session.flush()
        await self._audit(
            actor, "ai_task_config_update", config.id, before, self._task_snapshot(config)
        )

    async def create_prompt(
        self, portal_slug: str, task: str, payload: PromptVersionCreate, actor: str
    ) -> PromptVersionView:
        portal = await self._portal(portal_slug)
        if task not in TASKS:
            raise AIAdminNotFoundError("AI task not found")
        definition = await self._portal_prompt_definition(portal.id, task, create=True)
        assert definition is not None
        max_version = await self.session.scalar(
            select(func.max(PromptVersion.version)).where(
                PromptVersion.prompt_definition_id == definition.id
            )
        )
        version = PromptVersion(
            prompt_definition_id=definition.id,
            version=(max_version or 0) + 1,
            template=payload.template,
            status="draft",
            created_by=actor,
            notes=payload.notes,
        )
        self.session.add(version)
        await self.session.flush()
        await self._audit(
            actor,
            "ai_prompt_version_create",
            version.id,
            {},
            {"task": task, "version": version.version, "status": version.status},
        )
        return PromptVersionView(
            id=version.id,
            version=version.version,
            status=version.status,
            template=version.template,
            notes=version.notes,
            created_at=version.created_at,
            created_by=version.created_by,
            scope="portal",
        )

    async def activate_prompt(
        self, portal_slug: str, task: str, version_id: UUID, actor: str
    ) -> None:
        portal = await self._portal(portal_slug)
        definition = await self._portal_prompt_definition(portal.id, task, create=False)
        if definition is None:
            raise AIAdminNotFoundError("portal prompt not found")
        target = await self.session.scalar(
            select(PromptVersion).where(
                PromptVersion.id == version_id,
                PromptVersion.prompt_definition_id == definition.id,
            )
        )
        if target is None:
            raise AIAdminNotFoundError("portal prompt version not found")
        versions = list(
            (
                await self.session.scalars(
                    select(PromptVersion).where(PromptVersion.prompt_definition_id == definition.id)
                )
            ).all()
        )
        before = {str(item.id): item.status for item in versions}
        target.status = "active"
        config = await self.session.scalar(
            select(AITaskConfig).where(
                AITaskConfig.portal_id == portal.id,
                AITaskConfig.task == task,
            )
        )
        if config is None:
            defaults = TaskManager(self.settings).get(task)
            config = AITaskConfig(
                portal_id=portal.id,
                task=task,
                primary_model=defaults.primary_model,
                fallback_models=list(defaults.fallback_models),
                allowed_providers=sorted(defaults.allowed_providers),
                max_cost=defaults.max_cost,
                max_input_tokens=defaults.max_input_tokens,
                max_output_tokens=defaults.max_output_tokens,
                max_retries=defaults.max_retries,
                timeout_seconds=Decimal(str(defaults.timeout_seconds)),
                prompt_version=target.version,
                updated_by=actor,
            )
            self.session.add(config)
        else:
            config.prompt_version = target.version
            config.updated_by = actor
        await self.session.flush()
        await self._audit(
            actor,
            "ai_prompt_version_activate",
            target.id,
            before,
            {str(item.id): item.status for item in versions},
        )

    async def update_experiment(
        self, portal_slug: str, task: str, payload: ExperimentUpdate, actor: str
    ) -> None:
        portal = await self._portal(portal_slug)
        if task not in TASKS:
            raise AIAdminNotFoundError("AI task not found")
        definition = await self._portal_prompt_definition(portal.id, task, create=False)
        if definition is None:
            raise AIAdminValidationError("create portal-scoped prompt versions before A/B testing")
        versions = (
            await self.session.scalars(
                select(PromptVersion).where(
                    PromptVersion.prompt_definition_id == definition.id,
                    PromptVersion.id.in_(
                        [payload.prompt_version_a_id, payload.prompt_version_b_id]
                    ),
                    PromptVersion.status == "active",
                )
            )
        ).all()
        if len(versions) != 2:
            raise AIAdminValidationError(
                "both prompt variants must be active versions for this portal"
            )
        experiment = await self.session.scalar(
            select(AIExperiment).where(
                AIExperiment.portal_id == portal.id, AIExperiment.task == task
            )
        )
        before = self._experiment_snapshot(experiment)
        if experiment is None:
            experiment = AIExperiment(
                portal_id=portal.id,
                task=task,
                created_by=actor,
                **payload.model_dump(),
            )
            self.session.add(experiment)
        else:
            for key, value in payload.model_dump().items():
                setattr(experiment, key, value)
        await self.session.flush()
        await self._audit(
            actor,
            "ai_experiment_update",
            experiment.id,
            before,
            self._experiment_snapshot(experiment),
        )

    async def _portal(self, slug: str) -> Portal:
        portal = await self.session.scalar(select(Portal).where(Portal.slug == slug))
        if portal is None:
            raise AIAdminNotFoundError("portal not found")
        return portal

    async def _portal_prompt_definition(
        self, portal_id: UUID, task: str, *, create: bool
    ) -> PromptDefinition | None:
        definition = await self.session.scalar(
            select(PromptDefinition).where(
                PromptDefinition.task == task,
                PromptDefinition.portal_id == portal_id,
            )
        )
        if definition is None and create:
            definition = PromptDefinition(task=task, portal_id=portal_id)
            self.session.add(definition)
            await self.session.flush()
        return definition

    @staticmethod
    def _task_snapshot(config: AITaskConfig | None) -> dict[str, Any]:
        if config is None:
            return {}
        return {
            "primary_model": config.primary_model,
            "fallback_models": config.fallback_models,
            "allowed_providers": config.allowed_providers,
            "max_cost": str(config.max_cost),
            "max_input_tokens": config.max_input_tokens,
            "max_output_tokens": config.max_output_tokens,
            "max_retries": config.max_retries,
            "timeout_seconds": float(config.timeout_seconds),
            "prompt_version": config.prompt_version,
        }

    @staticmethod
    def _experiment_snapshot(experiment: AIExperiment | None) -> dict[str, Any]:
        if experiment is None:
            return {}
        return {
            "name": experiment.name,
            "prompt_version_a_id": str(experiment.prompt_version_a_id),
            "prompt_version_b_id": str(experiment.prompt_version_b_id),
            "variant_b_percent": experiment.variant_b_percent,
            "status": experiment.status,
        }

    async def _audit(
        self,
        actor: str,
        action: str,
        entity_id: UUID,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        self.session.add(
            EditorialAuditLog(
                actor=actor,
                action=action,
                entity_type="ai_admin",
                entity_id=entity_id,
                before=before,
                after=after,
            )
        )
