from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, and_, case, exists, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from news_platform.modules.analytics.domain.models import (
    BehaviorEvent,
    BehaviorEventAggregation,
    BehaviorEventType,
)
from news_platform.modules.community.domain.models import Follow
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentTopic,
)
from news_platform.modules.feeds.domain.schemas import FeedKind, PublicFeedPage
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.application.service import PublicSiteService
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository
from news_platform.modules.recommendations.domain.cursor import RecommendationCursor
from news_platform.modules.recommendations.domain.models import (
    PersonalizationTargetType,
    RecommendationGeneration,
    RecommendationSignalReceipt,
    UserAffinity,
    UserInterest,
)
from news_platform.modules.recommendations.domain.schemas import (
    AffinityBatchResult,
    InterestCatalog,
    InterestOption,
    UserInterestsUpdate,
    UserInterestsView,
    UserInterestView,
)
from news_platform.modules.users.application.service import AuthenticatedUser


class RecommendationsDisabledError(Exception):
    pass


class RecommendationTargetNotFoundError(Exception):
    pass


DEFAULT_SIGNAL_WEIGHTS = {
    "impression": 0.10,
    "click": 1.00,
    "content_open": 2.00,
    "scroll": 1.50,
    "video_start": 1.50,
    "watch_time": 2.00,
    "completion": 4.00,
    "share": 5.00,
}


def decayed_affinity_score(
    score: float, updated_at: datetime, now: datetime, half_life_days: float
) -> float:
    age_days = max((now - updated_at).total_seconds() / 86400.0, 0.0)
    return score * math.pow(0.5, age_days / max(half_life_days, 0.01))


def _enabled(portal: Portal) -> None:
    if (
        portal.feature_flags.get("recommendations") is False
        or portal.feature_flags.get("personalization") is False
    ):
        raise RecommendationsDisabledError("recommendations are disabled")


async def recommendation_generation(session: AsyncSession, portal_id: UUID, user_id: UUID) -> int:
    value = await session.scalar(
        select(RecommendationGeneration.generation).where(
            RecommendationGeneration.portal_id == portal_id,
            RecommendationGeneration.user_id == user_id,
        )
    )
    return int(value or 0)


async def bump_recommendation_generation(
    session: AsyncSession, portal_id: UUID, user_id: UUID
) -> None:
    await session.execute(
        pg_insert(RecommendationGeneration)
        .values(portal_id=portal_id, user_id=user_id, generation=1)
        .on_conflict_do_update(
            index_elements=[RecommendationGeneration.portal_id, RecommendationGeneration.user_id],
            set_={"generation": RecommendationGeneration.generation + 1, "updated_at": func.now()},
        )
    )


class UserInterestService:
    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)

    async def get(self, auth: AuthenticatedUser) -> UserInterestsView:
        _enabled(auth.portal)
        rows = list(
            (
                await self.session.scalars(
                    select(UserInterest)
                    .where(
                        UserInterest.portal_id == auth.portal.id,
                        UserInterest.user_id == auth.user.id,
                    )
                    .order_by(UserInterest.target_type, UserInterest.target_id)
                )
            ).all()
        )
        return UserInterestsView(
            items=[
                UserInterestView(
                    target_type=PersonalizationTargetType(row.target_type),
                    target_id=row.target_id,
                    weight=row.weight,
                )
                for row in rows
            ]
        )

    async def catalog(self, auth: AuthenticatedUser) -> InterestCatalog:
        _enabled(auth.portal)
        categories = await PublicSiteRepository(self.session).portal_categories(auth.portal)
        return InterestCatalog(
            items=[
                InterestOption(
                    target_type=PersonalizationTargetType.CATEGORY,
                    target_id=item.id,
                    name=item.name,
                )
                for item in categories
            ]
        )

    async def replace(
        self, auth: AuthenticatedUser, payload: UserInterestsUpdate
    ) -> UserInterestsView:
        _enabled(auth.portal)
        normalized = {
            (item.target_type.value, item.target_id): item.weight for item in payload.items
        }
        if len(normalized) != len(payload.items):
            raise ValueError("duplicate interest target")
        for target_type, target_id in normalized:
            if not await self._valid_target(auth.portal, target_type, target_id):
                raise RecommendationTargetNotFoundError("interest target not found in portal")
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"recommendations:{auth.portal.id}:{auth.user.id}", 0)
                )
            )
        )
        existing = list(
            (
                await self.session.scalars(
                    select(UserInterest)
                    .where(
                        UserInterest.portal_id == auth.portal.id,
                        UserInterest.user_id == auth.user.id,
                    )
                    .with_for_update()
                )
            ).all()
        )
        current = {(row.target_type, row.target_id): row.weight for row in existing}
        if current != normalized:
            for row in existing:
                await self.session.delete(row)
            self.session.add_all(
                [
                    UserInterest(
                        portal_id=auth.portal.id,
                        user_id=auth.user.id,
                        target_type=kind,
                        target_id=target,
                        weight=weight,
                    )
                    for (kind, target), weight in normalized.items()
                ]
            )
            await bump_recommendation_generation(self.session, auth.portal.id, auth.user.id)
            await self.session.flush()
        return await self.get(auth)

    async def _valid_target(self, portal: Portal, target_type: str, target_id: UUID) -> bool:
        eligible = (
            PublicSiteRepository(self.session)
            .eligible_statement(portal, self.now)
            .with_only_columns(ContentItem.id)
        )
        if target_type == "category":
            statement = select(ContentCategory.content_item_id).where(
                ContentCategory.category_id == target_id,
                ContentCategory.content_item_id.in_(eligible),
            )
        elif target_type == "topic":
            statement = select(ContentTopic.content_item_id).where(
                ContentTopic.topic_id == target_id,
                ContentTopic.content_item_id.in_(eligible),
            )
        elif target_type == "entity":
            statement = select(ContentEntity.content_item_id).where(
                ContentEntity.entity_id == target_id,
                ContentEntity.content_item_id.in_(eligible),
            )
        else:
            statement = select(ContentGeography.content_item_id).where(
                ContentGeography.geography_id == target_id,
                ContentGeography.content_item_id.in_(eligible),
            )
        return await self.session.scalar(select(statement.exists())) is True


class AffinityAggregationService:
    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)

    async def process_batch(self, limit: int) -> AffinityBatchResult:
        events = list(
            (
                await self.session.scalars(
                    select(BehaviorEvent)
                    .where(
                        BehaviorEvent.user_id.is_not(None),
                        ~exists().where(RecommendationSignalReceipt.event_id == BehaviorEvent.id),
                    )
                    .order_by(BehaviorEvent.timestamp, BehaviorEvent.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        applied = 0
        for event in events:
            did_apply = await self._apply(event)
            self.session.add(RecommendationSignalReceipt(event_id=event.id, applied=did_apply))
            applied += int(did_apply)
        await self.session.flush()
        return AffinityBatchResult(processed=len(events), applied=applied)

    async def _apply(self, event: BehaviorEvent) -> bool:
        if (
            event.user_id is None
            or event.content_id is None
            or event.event_type not in DEFAULT_SIGNAL_WEIGHTS
        ):
            return False
        portal = await self.session.get(Portal, event.portal_id)
        if portal is None:
            return False
        public_id = await self.session.scalar(
            PublicSiteRepository(self.session)
            .eligible_statement(portal, self.now)
            .where(ContentItem.id == event.content_id)
            .with_only_columns(ContentItem.id)
        )
        if public_id is None:
            return False
        configured = portal.ranking_settings.get("recommendations", {}).get("signals", {})
        weight = float(configured.get(event.event_type, DEFAULT_SIGNAL_WEIGHTS[event.event_type]))
        if event.event_type == BehaviorEventType.SCROLL.value:
            weight *= min(float(event.properties.get("percent", 0)) / 100.0, 1.0)
        elif event.event_type == BehaviorEventType.WATCH_TIME.value:
            weight *= min(float(event.properties.get("seconds", 0)) / 60.0, 5.0)
        if weight <= 0:
            return False
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"recommendations:{event.portal_id}:{event.user_id}", 0)
                )
            )
        )
        target_queries = (
            (
                "category",
                select(ContentCategory.category_id).where(
                    ContentCategory.content_item_id == event.content_id
                ),
            ),
            (
                "entity",
                select(ContentEntity.entity_id).where(
                    ContentEntity.content_item_id == event.content_id
                ),
            ),
            (
                "geography",
                select(ContentGeography.geography_id).where(
                    ContentGeography.content_item_id == event.content_id
                ),
            ),
        )
        changed = False
        half_life_days = float(
            portal.ranking_settings.get("recommendations", {}).get("affinity_half_life_days", 30.0)
        )
        for target_type, statement in target_queries:
            for target_id in (await self.session.scalars(statement)).all():
                key = {
                    "portal_id": event.portal_id,
                    "user_id": event.user_id,
                    "target_type": target_type,
                    "target_id": target_id,
                }
                row = await self.session.get(UserAffinity, key, with_for_update=True)
                if row is None:
                    self.session.add(
                        UserAffinity(**key, score=min(weight, 100.0), updated_at=self.now)
                    )
                else:
                    row.score = min(
                        decayed_affinity_score(
                            float(row.score), row.updated_at, self.now, half_life_days
                        )
                        + weight,
                        100.0,
                    )
                    row.updated_at = self.now
                changed = True
        if changed:
            await bump_recommendation_generation(self.session, event.portal_id, event.user_id)
        return changed


class RecommendationFeedService:
    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)
        self.public = PublicSiteService(session, now=self.now)

    async def page(
        self,
        auth: AuthenticatedUser,
        feed: FeedKind,
        *,
        language: str,
        limit: int,
        cursor_value: str | None,
    ) -> PublicFeedPage:
        _enabled(auth.portal)
        if language not in auth.portal.supported_languages:
            raise RecommendationTargetNotFoundError("language not supported by portal")
        generation = await recommendation_generation(self.session, auth.portal.id, auth.user.id)
        cursor = (
            RecommendationCursor.decode(
                cursor_value,
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                feed=feed.value,
                language=language,
                generation=generation,
            )
            if cursor_value
            else None
        )
        snapshot = cursor.snapshot_at if cursor else self.now
        if feed == FeedKind.FOR_YOU:
            contents, scores, has_more = await self._for_you(
                auth, language, limit, cursor, snapshot
            )
        elif feed == FeedKind.FOLLOWING:
            contents, scores, has_more = await self._following(
                auth, language, limit, cursor, snapshot
            )
        else:
            raise ValueError("unsupported personalized feed")
        records = await self.public.repository.hydrate(contents)
        categories = await self.public.repository.portal_categories(auth.portal)
        next_cursor = None
        if has_more and contents:
            last = contents[-1]
            if last.site_published_at is None:
                raise RuntimeError("public eligibility invariant violated")
            next_cursor = RecommendationCursor(
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                feed=feed.value,
                language=language,
                generation=generation,
                snapshot_at=snapshot,
                published_at=last.site_published_at,
                content_id=last.id,
                score=scores[-1],
            ).encode()
        portal_view = self.public.portal_view(auth.portal, categories)
        return PublicFeedPage(
            portal=portal_view,
            feed=feed,
            scope=None,
            label="For You" if feed == FeedKind.FOR_YOU else "Following",
            language=language,
            canonical_url=(
                f"{portal_view.canonical_url}/"
                f"{'for-you' if feed == FeedKind.FOR_YOU else 'following'}"
            ),
            items=[self.public.story_summary(auth.portal, record) for record in records],
            next_cursor=next_cursor,
        )

    @staticmethod
    def _target_match(
        target_type: InstrumentedAttribute[str], target_id: InstrumentedAttribute[UUID]
    ) -> ColumnElement[bool]:
        return or_(
            and_(
                target_type == "category",
                exists()
                .where(
                    ContentCategory.content_item_id == ContentItem.id,
                    ContentCategory.category_id == target_id,
                )
                .correlate(ContentItem, target_type.class_),
            ),
            and_(
                target_type == "topic",
                exists()
                .where(
                    ContentTopic.content_item_id == ContentItem.id,
                    ContentTopic.topic_id == target_id,
                )
                .correlate(ContentItem, target_type.class_),
            ),
            and_(
                target_type == "entity",
                exists()
                .where(
                    ContentEntity.content_item_id == ContentItem.id,
                    ContentEntity.entity_id == target_id,
                )
                .correlate(ContentItem, target_type.class_),
            ),
            and_(
                target_type == "geography",
                exists()
                .where(
                    ContentGeography.content_item_id == ContentItem.id,
                    ContentGeography.geography_id == target_id,
                )
                .correlate(ContentItem, target_type.class_),
            ),
        )

    async def _for_you(
        self,
        auth: AuthenticatedUser,
        language: str,
        limit: int,
        cursor: RecommendationCursor | None,
        snapshot: datetime,
    ) -> tuple[list[ContentItem], list[Decimal | None], bool]:
        age_days = func.greatest(
            func.extract("epoch", snapshot - UserAffinity.updated_at) / 86400.0, 0.0
        )
        half_life = float(
            auth.portal.ranking_settings.get("recommendations", {}).get(
                "affinity_half_life_days", 30.0
            )
        )
        affinity = (
            select(
                func.coalesce(
                    func.sum(UserAffinity.score * func.power(0.5, age_days / max(half_life, 0.01))),
                    0,
                )
            )
            .where(
                UserAffinity.portal_id == auth.portal.id,
                UserAffinity.user_id == auth.user.id,
                self._target_match(UserAffinity.target_type, UserAffinity.target_id),
            )
            .correlate(ContentItem)
            .scalar_subquery()
        )
        interests = (
            select(func.coalesce(func.sum(UserInterest.weight * 4.0), 0))
            .where(
                UserInterest.portal_id == auth.portal.id,
                UserInterest.user_id == auth.user.id,
                self._target_match(UserInterest.target_type, UserInterest.target_id),
            )
            .correlate(ContentItem)
            .scalar_subquery()
        )
        follows = (
            select(func.count(Follow.id) * 12.0)
            .where(
                Follow.portal_id == auth.portal.id,
                Follow.user_id == auth.user.id,
                self._target_match(Follow.target_type, Follow.target_id),
            )
            .correlate(ContentItem)
            .scalar_subquery()
        )
        engagement = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (BehaviorEvent.event_type == "impression", 0.1),
                            (BehaviorEvent.event_type == "click", 1.0),
                            (BehaviorEvent.event_type == "content_open", 2.0),
                            (BehaviorEvent.event_type == "completion", 4.0),
                            (BehaviorEvent.event_type == "share", 5.0),
                            else_=0.0,
                        )
                    ),
                    0,
                )
            )
            .join(
                BehaviorEventAggregation,
                BehaviorEventAggregation.event_id == BehaviorEvent.id,
            )
            .where(
                BehaviorEvent.portal_id == auth.portal.id,
                BehaviorEvent.content_id == ContentItem.id,
                BehaviorEventAggregation.aggregated_at <= snapshot,
            )
            .correlate(ContentItem)
            .scalar_subquery()
        )
        content_age = func.greatest(
            func.extract("epoch", snapshot - ContentItem.site_published_at) / 3600.0, 0.0
        )
        score = func.round(
            sql_cast(
                (affinity + interests + follows + func.ln(1 + engagement) * 2.0)
                / (1.0 + content_age / 72.0),
                Numeric,
            ),
            6,
        ).label("recommendation_score")
        statement = (
            self.public.repository.eligible_statement(auth.portal, snapshot)
            .with_only_columns(ContentItem, score)
            .where(ContentItem.primary_language == language)
        )
        if cursor:
            if cursor.score is None:
                raise ValueError("For You cursor requires score")
            statement = statement.where(
                or_(
                    score < cursor.score,
                    and_(
                        score == cursor.score,
                        or_(
                            ContentItem.site_published_at < cursor.published_at,
                            and_(
                                ContentItem.site_published_at == cursor.published_at,
                                ContentItem.id < cursor.content_id,
                            ),
                        ),
                    ),
                )
            )
        rows = (
            await self.session.execute(
                statement.order_by(
                    score.desc(), ContentItem.site_published_at.desc(), ContentItem.id.desc()
                ).limit(limit + 1)
            )
        ).all()
        scores: list[Decimal | None] = [Decimal(str(row[1])) for row in rows[:limit]]
        return [row[0] for row in rows[:limit]], scores, len(rows) > limit

    async def _following(
        self,
        auth: AuthenticatedUser,
        language: str,
        limit: int,
        cursor: RecommendationCursor | None,
        snapshot: datetime,
    ) -> tuple[list[ContentItem], list[Decimal | None], bool]:
        matches = exists().where(
            Follow.portal_id == auth.portal.id,
            Follow.user_id == auth.user.id,
            self._target_match(Follow.target_type, Follow.target_id),
        )
        statement = self.public.repository.eligible_statement(auth.portal, snapshot).where(
            ContentItem.primary_language == language, matches
        )
        if cursor:
            statement = statement.where(
                or_(
                    ContentItem.site_published_at < cursor.published_at,
                    and_(
                        ContentItem.site_published_at == cursor.published_at,
                        ContentItem.id < cursor.content_id,
                    ),
                )
            )
        contents = list(
            (
                await self.session.scalars(
                    statement.order_by(
                        ContentItem.site_published_at.desc(), ContentItem.id.desc()
                    ).limit(limit + 1)
                )
            ).all()
        )
        return contents[:limit], [None] * min(len(contents), limit), len(contents) > limit


async def process_affinities_once(
    session_factory: async_sessionmaker[AsyncSession], batch_size: int
) -> AffinityBatchResult:
    async with session_factory() as session, session.begin():
        return await AffinityAggregationService(session).process_batch(batch_size)
