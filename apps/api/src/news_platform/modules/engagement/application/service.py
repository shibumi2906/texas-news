from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import ContentItem
from news_platform.modules.engagement.domain.models import (
    ContentEngagementCounter,
    EngagementCounterUpdate,
    EngagementMetric,
)
from news_platform.modules.engagement.domain.schemas import CounterReceipt


class EngagementContentNotFoundError(Exception):
    pass


class EngagementIdempotencyConflictError(Exception):
    pass


class EngagementCounterService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def increment(
        self,
        *,
        content_id: UUID,
        metric: EngagementMetric,
        amount: int,
        idempotency_key: str,
    ) -> CounterReceipt:
        if await self.session.get(ContentItem, content_id) is None:
            raise EngagementContentNotFoundError("content item not found")

        inserted_receipt = await self.session.scalar(
            postgresql_insert(EngagementCounterUpdate)
            .values(
                idempotency_key=idempotency_key,
                content_item_id=content_id,
                metric=metric.value,
                amount=amount,
            )
            .on_conflict_do_nothing(index_elements=[EngagementCounterUpdate.idempotency_key])
            .returning(EngagementCounterUpdate.id)
        )
        if inserted_receipt is None:
            receipt = await self.session.scalar(
                select(EngagementCounterUpdate).where(
                    EngagementCounterUpdate.idempotency_key == idempotency_key
                )
            )
            if receipt is None:
                raise RuntimeError("idempotency receipt disappeared")
            if (
                receipt.content_item_id != content_id
                or receipt.metric != metric.value
                or receipt.amount != amount
            ):
                raise EngagementIdempotencyConflictError(
                    "idempotency key was already used for a different counter update"
                )
            return CounterReceipt(
                content_id=content_id,
                metric=metric,
                value=await self._value(content_id, metric),
                applied=False,
            )

        column = getattr(ContentEngagementCounter, metric.value)
        statement = (
            postgresql_insert(ContentEngagementCounter)
            .values(content_item_id=content_id, **{metric.value: amount})
            .on_conflict_do_update(
                index_elements=[ContentEngagementCounter.content_item_id],
                set_={metric.value: column + amount, "updated_at": func.now()},
            )
            .returning(column)
        )
        value = await self.session.scalar(statement)
        return CounterReceipt(
            content_id=content_id,
            metric=metric,
            value=value or 0,
            applied=True,
        )

    async def _value(self, content_id: UUID, metric: EngagementMetric) -> int:
        value = await self.session.scalar(
            select(getattr(ContentEngagementCounter, metric.value)).where(
                ContentEngagementCounter.content_item_id == content_id
            )
        )
        return value or 0
