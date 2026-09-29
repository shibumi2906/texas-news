from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.ai.domain.models import (
    AIExperiment,
    AIResult,
    AITaskConfig,
    PromptDefinition,
    PromptVersion,
)


class AIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active_prompt(
        self, task: str, version: int, portal_id: UUID | None = None
    ) -> PromptVersion | None:
        scope = PromptDefinition.portal_id == portal_id if portal_id else None
        statement = (
            select(PromptVersion)
            .join(PromptDefinition, PromptDefinition.id == PromptVersion.prompt_definition_id)
            .where(
                PromptDefinition.task == task,
                PromptVersion.version == version,
                PromptVersion.status == "active",
            )
        )
        if scope is not None:
            statement = statement.where(scope)
        else:
            statement = statement.where(PromptDefinition.portal_id.is_(None))
        return cast(
            PromptVersion | None,
            await self.session.scalar(statement),
        )

    async def task_config(self, portal_id: UUID, task: str) -> AITaskConfig | None:
        return cast(
            AITaskConfig | None,
            await self.session.scalar(
                select(AITaskConfig).where(
                    AITaskConfig.portal_id == portal_id, AITaskConfig.task == task
                )
            ),
        )

    async def experiment(self, portal_id: UUID, task: str) -> AIExperiment | None:
        return cast(
            AIExperiment | None,
            await self.session.scalar(
                select(AIExperiment).where(
                    AIExperiment.portal_id == portal_id,
                    AIExperiment.task == task,
                    AIExperiment.status == "running",
                )
            ),
        )

    async def lock_cache_key(self, cache_key: str) -> None:
        raw = int.from_bytes(hashlib.sha256(cache_key.encode()).digest()[:8], "big")
        lock_id = raw if raw < 2**63 else raw - 2**64
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id}
        )

    async def cached_result(self, cache_key: str, now: datetime) -> AIResult | None:
        return cast(
            AIResult | None,
            await self.session.scalar(
                select(AIResult).where(AIResult.cache_key == cache_key, AIResult.expires_at > now)
            ),
        )

    async def remove_expired_result(self, cache_key: str, now: datetime) -> None:
        await self.session.execute(
            delete(AIResult).where(AIResult.cache_key == cache_key, AIResult.expires_at <= now)
        )
