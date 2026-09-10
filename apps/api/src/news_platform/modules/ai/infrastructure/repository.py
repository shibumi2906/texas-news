from __future__ import annotations

import hashlib
from datetime import datetime
from typing import cast

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.ai.domain.models import AIResult, PromptDefinition, PromptVersion


class AIRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active_prompt(self, task: str, version: int) -> PromptVersion | None:
        return cast(
            PromptVersion | None,
            await self.session.scalar(
                select(PromptVersion)
                .join(
                    PromptDefinition,
                    PromptDefinition.id == PromptVersion.prompt_definition_id,
                )
                .where(
                    PromptDefinition.task == task,
                    PromptVersion.version == version,
                    PromptVersion.status == "active",
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
