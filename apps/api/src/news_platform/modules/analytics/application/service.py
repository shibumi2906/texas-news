from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from news_platform.modules.analytics.domain.models import (
    BehaviorEvent,
    BehaviorEventAggregation,
    BehaviorEventType,
)
from news_platform.modules.analytics.domain.schemas import (
    AggregationBatchResult,
    BehaviorEventCreate,
    BehaviorEventReceipt,
    InvalidationBatchResult,
)
from news_platform.modules.content.domain.models import ContentItem
from news_platform.modules.engagement.application.service import EngagementCounterService
from news_platform.modules.engagement.domain.models import EngagementMetric
from news_platform.modules.entities.domain.models import Entity
from news_platform.modules.feeds.infrastructure.cache import CACHE_EPOCH_KEY
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository


class AnalyticsResourceNotFoundError(Exception):
    pass


class AnalyticsIdempotencyConflictError(Exception):
    pass


class AnalyticsTimestampError(Exception):
    pass


class AnalyticsIngestionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        now: datetime | None = None,
        max_age_days: int = 7,
        future_skew_seconds: int = 300,
    ) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)
        self.max_age = timedelta(days=max_age_days)
        self.future_skew = timedelta(seconds=future_skew_seconds)

    async def collect(self, portal_slug: str, payload: BehaviorEventCreate) -> BehaviorEventReceipt:
        portal = await self.session.scalar(
            select(Portal).where(Portal.slug == portal_slug, Portal.status == PortalStatus.ACTIVE)
        )
        if portal is None:
            raise AnalyticsResourceNotFoundError("portal not found")
        occurred_at = payload.timestamp.astimezone(UTC)
        if occurred_at < self.now - self.max_age or occurred_at > self.now + self.future_skew:
            raise AnalyticsTimestampError("event timestamp is outside the accepted window")

        if payload.content_id is not None:
            content = await self.session.scalar(
                PublicSiteRepository(self.session)
                .eligible_statement(portal, self.now)
                .where(ContentItem.id == payload.content_id)
            )
            if content is None:
                raise AnalyticsResourceNotFoundError("public content not found in portal")
        if (
            payload.entity_id is not None
            and await self.session.get(Entity, payload.entity_id) is None
        ):
            raise AnalyticsResourceNotFoundError("entity not found")
        if payload.geography_id is not None and not await self._geography_in_portal(
            portal, payload.geography_id
        ):
            raise AnalyticsResourceNotFoundError("geography not found in portal")

        inserted = await self.session.scalar(
            postgresql_insert(BehaviorEvent)
            .values(
                id=payload.id,
                portal_id=portal.id,
                user_id=None,
                anonymous_id=payload.anonymous_id,
                session_id=payload.session_id,
                event_type=payload.event_type.value,
                content_id=payload.content_id,
                entity_id=payload.entity_id,
                geography_id=payload.geography_id,
                timestamp=occurred_at,
                properties=payload.properties,
            )
            .on_conflict_do_nothing(index_elements=[BehaviorEvent.id])
            .returning(BehaviorEvent.id)
        )
        if inserted is not None:
            return BehaviorEventReceipt(id=payload.id, status="accepted")

        existing = await self.session.get(BehaviorEvent, payload.id)
        if existing is None:
            raise RuntimeError("behavior event disappeared after idempotency conflict")
        if not self._same_event(existing, portal.id, payload, occurred_at):
            raise AnalyticsIdempotencyConflictError(
                "event id was already used for a different event"
            )
        return BehaviorEventReceipt(id=payload.id, status="duplicate")

    async def _geography_in_portal(self, portal: Portal, geography_id: UUID) -> bool:
        if portal.primary_geography_id is None:
            return False
        scope = (
            select(GeographyNode.id)
            .where(GeographyNode.id == portal.primary_geography_id)
            .cte(name="analytics_portal_geography", recursive=True)
        )
        scope = scope.union_all(
            select(GeographyNode.id).join(scope, GeographyNode.parent_id == scope.c.id)
        )
        return (
            await self.session.scalar(select(scope.c.id).where(scope.c.id == geography_id).limit(1))
            is not None
        )

    @staticmethod
    def _same_event(
        existing: BehaviorEvent,
        portal_id: UUID,
        payload: BehaviorEventCreate,
        occurred_at: datetime,
    ) -> bool:
        return (
            existing.portal_id == portal_id
            and existing.user_id is None
            and existing.anonymous_id == payload.anonymous_id
            and existing.session_id == payload.session_id
            and existing.event_type == payload.event_type.value
            and existing.content_id == payload.content_id
            and existing.entity_id == payload.entity_id
            and existing.geography_id == payload.geography_id
            and existing.timestamp == occurred_at
            and existing.properties == payload.properties
        )


class AnalyticsAggregationService:
    METRICS = {
        BehaviorEventType.IMPRESSION: EngagementMetric.IMPRESSIONS,
        BehaviorEventType.CLICK: EngagementMetric.CLICKS,
        BehaviorEventType.CONTENT_OPEN: EngagementMetric.VIEWS,
        BehaviorEventType.WATCH_TIME: EngagementMetric.WATCH_TIME_SECONDS,
        BehaviorEventType.COMPLETION: EngagementMetric.COMPLETIONS,
        BehaviorEventType.SHARE: EngagementMetric.SHARES,
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def aggregate_batch(self, limit: int) -> AggregationBatchResult:
        processed = list(
            (
                await self.session.scalars(
                    select(BehaviorEvent)
                    .where(~exists().where(BehaviorEventAggregation.event_id == BehaviorEvent.id))
                    .order_by(BehaviorEvent.timestamp, BehaviorEvent.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        ranking_updates = 0
        for event in processed:
            event_type = BehaviorEventType(event.event_type)
            metric = self.METRICS.get(event_type)
            ranking_changed = False
            if metric is not None and event.content_id is not None:
                amount = (
                    int(event.properties["seconds"])
                    if event_type is BehaviorEventType.WATCH_TIME
                    else 1
                )
                await EngagementCounterService(self.session).increment(
                    content_id=event.content_id,
                    metric=metric,
                    amount=amount,
                    idempotency_key=f"behavior-event:{event.id}:{metric.value}",
                )
                ranking_changed = True
                ranking_updates += 1
            self.session.add(
                BehaviorEventAggregation(
                    event_id=event.id,
                    ranking_changed=ranking_changed,
                    feed_invalidated_at=None if ranking_changed else func.now(),
                )
            )
        await self.session.flush()
        return AggregationBatchResult(processed=len(processed), ranking_updates=ranking_updates)

    async def deliver_invalidations(self, redis_client: Any, limit: int) -> InvalidationBatchResult:
        pending = list(
            (
                await self.session.scalars(
                    select(BehaviorEventAggregation)
                    .where(
                        BehaviorEventAggregation.ranking_changed.is_(True),
                        BehaviorEventAggregation.feed_invalidated_at.is_(None),
                    )
                    .order_by(BehaviorEventAggregation.aggregated_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        if not pending:
            return InvalidationBatchResult(delivered=0)
        await redis_client.incr(CACHE_EPOCH_KEY)
        delivered_at = datetime.now(UTC)
        for receipt in pending:
            receipt.feed_invalidated_at = delivered_at
        await self.session.flush()
        return InvalidationBatchResult(delivered=len(pending))


async def process_analytics_once(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Any, batch_size: int
) -> tuple[AggregationBatchResult, InvalidationBatchResult]:
    async with session_factory() as session, session.begin():
        aggregated = await AnalyticsAggregationService(session).aggregate_batch(batch_size)
    async with session_factory() as session, session.begin():
        invalidated = await AnalyticsAggregationService(session).deliver_invalidations(
            redis_client, batch_size
        )
    return aggregated, invalidated
