from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.advertising.domain.models import (
    AdCampaign,
    AdClick,
    AdCreative,
    AdImpression,
    AdPlacement,
    AdTargeting,
)
from news_platform.modules.advertising.domain.schemas import (
    AdDecision,
    AdvertisingOverview,
    CampaignView,
    CampaignWrite,
    ClickCreate,
    CreativeView,
    ImpressionCreate,
    PlacementView,
    PlacementWrite,
    TargetingView,
    TrackingReceipt,
)
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentGeography,
    ContentItem,
)
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository
from news_platform.modules.taxonomy.domain.models import Category


class AdvertisingNotFoundError(Exception):
    pass


class AdvertisingDisabledError(Exception):
    pass


class AdvertisingConflictError(Exception):
    pass


class AdvertisingValidationError(Exception):
    pass


class AdvertisingService:
    def __init__(self, session: AsyncSession, *, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)

    async def overview(self, portal_slug: str) -> AdvertisingOverview:
        portal = await self._portal(portal_slug, active_only=False)
        placements = list(
            (
                await self.session.scalars(
                    select(AdPlacement)
                    .where(AdPlacement.portal_id == portal.id)
                    .order_by(AdPlacement.code)
                )
            ).all()
        )
        campaigns = list(
            (
                await self.session.scalars(
                    select(AdCampaign)
                    .where(AdCampaign.portal_id == portal.id)
                    .order_by(AdCampaign.created_at, AdCampaign.id)
                )
            ).all()
        )
        impression_count = await self.session.scalar(
            select(func.count())
            .select_from(AdImpression)
            .where(AdImpression.portal_id == portal.id)
        )
        click_count = await self.session.scalar(
            select(func.count()).select_from(AdClick).where(AdClick.portal_id == portal.id)
        )
        return AdvertisingOverview(
            portal_slug=portal.slug,
            enabled=portal.feature_flags.get("advertising", False) is True,
            placements=[self._placement_view(item) for item in placements],
            campaigns=[await self._campaign_view(item) for item in campaigns],
            impressions=int(impression_count or 0),
            clicks=int(click_count or 0),
        )

    async def create_placement(
        self, portal_slug: str, payload: PlacementWrite, actor: str
    ) -> PlacementView:
        portal = await self._portal(portal_slug, active_only=False)
        if await self.session.scalar(
            select(AdPlacement.id).where(
                AdPlacement.portal_id == portal.id, AdPlacement.code == payload.code
            )
        ):
            raise AdvertisingConflictError("placement code already exists")
        placement = AdPlacement(portal_id=portal.id, **payload.model_dump())
        self.session.add(placement)
        await self.session.flush()
        await self._audit(
            actor, "ad_placement_create", placement.id, {}, payload.model_dump(mode="json")
        )
        return self._placement_view(placement)

    async def update_placement(
        self, portal_slug: str, placement_id: UUID, payload: PlacementWrite, actor: str
    ) -> PlacementView:
        portal = await self._portal(portal_slug, active_only=False)
        placement = await self.session.scalar(
            select(AdPlacement)
            .where(AdPlacement.id == placement_id, AdPlacement.portal_id == portal.id)
            .with_for_update()
        )
        if placement is None:
            raise AdvertisingNotFoundError("placement not found")
        duplicate = await self.session.scalar(
            select(AdPlacement.id).where(
                AdPlacement.portal_id == portal.id,
                AdPlacement.code == payload.code,
                AdPlacement.id != placement.id,
            )
        )
        if duplicate:
            raise AdvertisingConflictError("placement code already exists")
        before = self._placement_view(placement).model_dump(mode="json")
        for key, value in payload.model_dump().items():
            setattr(placement, key, value)
        await self.session.flush()
        await self._audit(
            actor, "ad_placement_update", placement.id, before, payload.model_dump(mode="json")
        )
        return self._placement_view(placement)

    async def create_campaign(
        self, portal_slug: str, payload: CampaignWrite, actor: str
    ) -> CampaignView:
        portal = await self._portal(portal_slug, active_only=False)
        await self._validate_targeting(portal, payload)
        campaign = AdCampaign(
            portal_id=portal.id,
            name=payload.name,
            status=payload.status,
            priority=payload.priority,
            starts_at=payload.starts_at.astimezone(UTC),
            ends_at=payload.ends_at.astimezone(UTC) if payload.ends_at else None,
        )
        self.session.add(campaign)
        await self.session.flush()
        self.session.add(AdTargeting(campaign_id=campaign.id, **self._target_values(payload)))
        for creative in payload.creatives:
            self.session.add(
                AdCreative(campaign_id=campaign.id, **creative.model_dump(mode="json"))
            )
        await self.session.flush()
        view = await self._campaign_view(campaign)
        await self._audit(
            actor, "ad_campaign_create", campaign.id, {}, view.model_dump(mode="json")
        )
        return view

    async def update_campaign(
        self, portal_slug: str, campaign_id: UUID, payload: CampaignWrite, actor: str
    ) -> CampaignView:
        portal = await self._portal(portal_slug, active_only=False)
        campaign = await self.session.scalar(
            select(AdCampaign)
            .where(AdCampaign.id == campaign_id, AdCampaign.portal_id == portal.id)
            .with_for_update()
        )
        if campaign is None:
            raise AdvertisingNotFoundError("campaign not found")
        await self._validate_targeting(portal, payload)
        before = (await self._campaign_view(campaign)).model_dump(mode="json")
        campaign.name = payload.name
        campaign.status = payload.status
        campaign.priority = payload.priority
        campaign.starts_at = payload.starts_at.astimezone(UTC)
        campaign.ends_at = payload.ends_at.astimezone(UTC) if payload.ends_at else None
        targeting = await self.session.scalar(
            select(AdTargeting).where(AdTargeting.campaign_id == campaign.id)
        )
        assert targeting is not None
        for key, value in self._target_values(payload).items():
            setattr(targeting, key, value)
        existing = list(
            (
                await self.session.scalars(
                    select(AdCreative).where(AdCreative.campaign_id == campaign.id)
                )
            ).all()
        )
        for existing_creative in existing:
            existing_creative.active = False
        for creative_payload in payload.creatives:
            self.session.add(
                AdCreative(
                    campaign_id=campaign.id,
                    **creative_payload.model_dump(mode="json"),
                )
            )
        await self.session.flush()
        view = await self._campaign_view(campaign)
        await self._audit(
            actor, "ad_campaign_update", campaign.id, before, view.model_dump(mode="json")
        )
        return view

    async def decide(
        self,
        portal_slug: str,
        placement_code: str,
        identity_key: str,
        *,
        language: str,
        content_id: UUID | None,
        geography_id: UUID | None,
        category_id: UUID | None,
        content_type: str | None,
    ) -> AdDecision | None:
        portal = await self._portal(portal_slug)
        if portal.feature_flags.get("advertising", False) is not True:
            raise AdvertisingDisabledError
        placement = await self.session.scalar(
            select(AdPlacement).where(
                AdPlacement.portal_id == portal.id,
                AdPlacement.code == placement_code,
                AdPlacement.active.is_(True),
            )
        )
        if placement is None:
            raise AdvertisingNotFoundError("placement not found")
        if content_id is not None:
            content = await self.session.scalar(
                PublicSiteRepository(self.session)
                .eligible_statement(portal, self.now)
                .where(ContentItem.id == content_id)
            )
            if content is None:
                raise AdvertisingNotFoundError("public content not found")
            content_type = content.content_type.value
            category_ids = set(
                (
                    await self.session.scalars(
                        select(ContentCategory.category_id).where(
                            ContentCategory.content_item_id == content.id
                        )
                    )
                ).all()
            )
            if category_id is not None and category_id not in category_ids:
                raise AdvertisingValidationError("category does not belong to content")
            geography_ids = set(
                (
                    await self.session.scalars(
                        select(ContentGeography.geography_id).where(
                            ContentGeography.content_item_id == content.id
                        )
                    )
                ).all()
            )
            if geography_id is not None and geography_id not in geography_ids:
                raise AdvertisingValidationError("geography does not belong to content")
        else:
            category_ids = {category_id} if category_id is not None else set()
            geography_ids = {geography_id} if geography_id is not None else set()
        if placement.allowed_content_types and content_type not in placement.allowed_content_types:
            return None
        if geography_id is not None and not await self._geography_in_portal(portal, geography_id):
            raise AdvertisingNotFoundError("geography not found in portal")
        if category_id is not None and not await self._category_in_portal(portal, category_id):
            raise AdvertisingNotFoundError("category not found in portal")
        if language not in portal.supported_languages:
            raise AdvertisingNotFoundError("language not found in portal")
        rows = (
            await self.session.execute(
                select(AdCampaign, AdTargeting)
                .join(AdTargeting, AdTargeting.campaign_id == AdCampaign.id)
                .where(
                    AdCampaign.portal_id == portal.id,
                    AdCampaign.status == "active",
                    AdCampaign.starts_at <= self.now,
                    (AdCampaign.ends_at.is_(None) | (AdCampaign.ends_at > self.now)),
                )
                .order_by(AdCampaign.priority.desc(), AdCampaign.id)
            )
        ).all()
        eligible: list[AdCampaign] = []
        for campaign, target in rows:
            if target.placement_codes and placement_code not in target.placement_codes:
                continue
            if target.languages and language not in target.languages:
                continue
            if target.geography_ids and (
                not geography_ids.intersection(UUID(value) for value in target.geography_ids)
            ):
                continue
            if target.category_ids and (
                not category_ids.intersection(UUID(value) for value in target.category_ids)
            ):
                continue
            if target.content_types and content_type not in target.content_types:
                continue
            eligible.append(campaign)
        if not eligible:
            return None
        top_priority = eligible[0].priority
        pool = [item for item in eligible if item.priority == top_priority]
        seed = f"{portal.id}:{placement.id}:{identity_key}:{content_id or ''}".encode()
        campaign = pool[int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") % len(pool)]
        creatives = list(
            (
                await self.session.scalars(
                    select(AdCreative)
                    .where(AdCreative.campaign_id == campaign.id, AdCreative.active.is_(True))
                    .order_by(AdCreative.id)
                )
            ).all()
        )
        if not creatives:
            return None
        creative = creatives[
            int.from_bytes(hashlib.sha256(seed + b":creative").digest()[:8], "big") % len(creatives)
        ]
        return AdDecision(
            placement_id=placement.id,
            campaign_id=campaign.id,
            creative_id=creative.id,
            format=creative.format,
            asset_url=creative.asset_url,
            click_url=creative.click_url,
            alt_text=creative.alt_text,
        )

    async def track_impression(
        self, portal_slug: str, payload: ImpressionCreate
    ) -> TrackingReceipt:
        portal = await self._portal(portal_slug)
        if portal.feature_flags.get("advertising", False) is not True:
            raise AdvertisingDisabledError
        occurred = self._valid_time(payload.occurred_at)
        existing = await self.session.get(AdImpression, payload.id)
        if existing is not None:
            same = (
                existing.portal_id == portal.id
                and existing.placement_id == payload.placement_id
                and existing.campaign_id == payload.campaign_id
                and existing.creative_id == payload.creative_id
                and existing.content_id == payload.content_id
                and existing.occurred_at == occurred
            )
            if not same:
                raise AdvertisingConflictError("tracking id already used for another event")
            return TrackingReceipt(id=payload.id, status="duplicate")
        placement = await self.session.scalar(
            select(AdPlacement).where(
                AdPlacement.id == payload.placement_id, AdPlacement.portal_id == portal.id
            )
        )
        campaign = await self.session.scalar(
            select(AdCampaign).where(
                AdCampaign.id == payload.campaign_id, AdCampaign.portal_id == portal.id
            )
        )
        creative = await self.session.scalar(
            select(AdCreative).where(
                AdCreative.id == payload.creative_id, AdCreative.campaign_id == payload.campaign_id
            )
        )
        if placement is None or campaign is None or creative is None:
            raise AdvertisingNotFoundError("ad delivery not found")
        if payload.content_id is not None:
            content = await self.session.scalar(
                PublicSiteRepository(self.session)
                .eligible_statement(portal, self.now)
                .where(ContentItem.id == payload.content_id)
            )
            if content is None:
                raise AdvertisingNotFoundError("public content not found")
        inserted = await self.session.scalar(
            postgresql_insert(AdImpression)
            .values(
                id=payload.id,
                portal_id=portal.id,
                placement_id=payload.placement_id,
                campaign_id=payload.campaign_id,
                creative_id=payload.creative_id,
                content_id=payload.content_id,
                occurred_at=occurred,
            )
            .on_conflict_do_nothing(index_elements=[AdImpression.id])
            .returning(AdImpression.id)
        )
        if inserted is None:
            raced = await self.session.get(AdImpression, payload.id)
            if raced is None or not (
                raced.portal_id == portal.id
                and raced.placement_id == payload.placement_id
                and raced.campaign_id == payload.campaign_id
                and raced.creative_id == payload.creative_id
                and raced.content_id == payload.content_id
                and raced.occurred_at == occurred
            ):
                raise AdvertisingConflictError("tracking id already used for another event")
            return TrackingReceipt(id=payload.id, status="duplicate")
        return TrackingReceipt(id=payload.id, status="accepted")

    async def track_click(self, portal_slug: str, payload: ClickCreate) -> TrackingReceipt:
        portal = await self._portal(portal_slug)
        if portal.feature_flags.get("advertising", False) is not True:
            raise AdvertisingDisabledError
        occurred = self._valid_time(payload.occurred_at)
        existing = await self.session.get(AdClick, payload.id)
        if existing is not None:
            if (
                existing.portal_id != portal.id
                or existing.impression_id != payload.impression_id
                or existing.occurred_at != occurred
            ):
                raise AdvertisingConflictError("tracking id already used for another event")
            return TrackingReceipt(id=payload.id, status="duplicate")
        impression = await self.session.scalar(
            select(AdImpression).where(
                AdImpression.id == payload.impression_id, AdImpression.portal_id == portal.id
            )
        )
        if impression is None:
            raise AdvertisingNotFoundError("impression not found")
        inserted = await self.session.scalar(
            postgresql_insert(AdClick)
            .values(
                id=payload.id,
                portal_id=portal.id,
                impression_id=payload.impression_id,
                occurred_at=occurred,
            )
            .on_conflict_do_nothing(index_elements=[AdClick.id])
            .returning(AdClick.id)
        )
        if inserted is None:
            raced = await self.session.get(AdClick, payload.id)
            if raced is None or not (
                raced.portal_id == portal.id
                and raced.impression_id == payload.impression_id
                and raced.occurred_at == occurred
            ):
                raise AdvertisingConflictError("tracking id already used for another event")
            return TrackingReceipt(id=payload.id, status="duplicate")
        return TrackingReceipt(id=payload.id, status="accepted")

    def _valid_time(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise AdvertisingValidationError("occurred_at must be timezone-aware")
        result = value.astimezone(UTC)
        if result < self.now - timedelta(days=7) or result > self.now + timedelta(minutes=5):
            raise AdvertisingValidationError("tracking timestamp is outside the accepted window")
        return result

    async def _validate_targeting(self, portal: Portal, payload: CampaignWrite) -> None:
        for code in payload.targeting.placement_codes:
            if (
                await self.session.scalar(
                    select(AdPlacement.id).where(
                        AdPlacement.portal_id == portal.id, AdPlacement.code == code
                    )
                )
                is None
            ):
                raise AdvertisingValidationError("target placement not found in portal")
        for geography_id in payload.targeting.geography_ids:
            if not await self._geography_in_portal(portal, geography_id):
                raise AdvertisingValidationError("target geography not found in portal")
        for category_id in payload.targeting.category_ids:
            if not await self._category_in_portal(portal, category_id):
                raise AdvertisingValidationError("target category not found in portal")
        unsupported = set(payload.targeting.languages) - set(portal.supported_languages)
        if unsupported:
            raise AdvertisingValidationError("target language is not supported by portal")

    async def _geography_in_portal(self, portal: Portal, geography_id: UUID) -> bool:
        if portal.primary_geography_id is None:
            return False
        scope = (
            select(GeographyNode.id)
            .where(GeographyNode.id == portal.primary_geography_id)
            .cte(name="advertising_portal_geography", recursive=True)
        )
        scope = scope.union_all(
            select(GeographyNode.id).join(scope, GeographyNode.parent_id == scope.c.id)
        )
        return (
            await self.session.scalar(select(scope.c.id).where(scope.c.id == geography_id).limit(1))
            is not None
        )

    async def _category_in_portal(self, portal: Portal, category_id: UUID) -> bool:
        category = await self.session.get(Category, category_id)
        if category is None:
            return False
        enabled = portal.category_settings.get("enabled", [])
        return not isinstance(enabled, list) or not enabled or category.slug in enabled

    async def _portal(self, slug: str, *, active_only: bool = True) -> Portal:
        statement = select(Portal).where(Portal.slug == slug)
        if active_only:
            statement = statement.where(Portal.status == PortalStatus.ACTIVE)
        portal = await self.session.scalar(statement)
        if portal is None:
            raise AdvertisingNotFoundError("portal not found")
        return portal

    @staticmethod
    def _placement_view(item: AdPlacement) -> PlacementView:
        return PlacementView(
            id=item.id,
            code=item.code,
            name=item.name,
            allowed_content_types=item.allowed_content_types,
            active=item.active,
        )

    async def _campaign_view(self, item: AdCampaign) -> CampaignView:
        target = await self.session.scalar(
            select(AdTargeting).where(AdTargeting.campaign_id == item.id)
        )
        creatives = list(
            (
                await self.session.scalars(
                    select(AdCreative)
                    .where(AdCreative.campaign_id == item.id)
                    .order_by(AdCreative.created_at, AdCreative.id)
                )
            ).all()
        )
        assert target is not None
        return CampaignView(
            id=item.id,
            name=item.name,
            status=item.status,
            priority=item.priority,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            targeting=TargetingView(
                placement_codes=target.placement_codes,
                geography_ids=[UUID(value) for value in target.geography_ids],
                languages=target.languages,
                category_ids=[UUID(value) for value in target.category_ids],
                content_types=target.content_types,
            ),
            creatives=[
                CreativeView(
                    id=value.id,
                    name=value.name,
                    format=value.format,
                    asset_url=value.asset_url,
                    click_url=value.click_url,
                    alt_text=value.alt_text,
                    active=value.active,
                )
                for value in creatives
            ],
        )

    @staticmethod
    def _target_values(payload: CampaignWrite) -> dict[str, Any]:
        return {
            "placement_codes": sorted(set(payload.targeting.placement_codes)),
            "geography_ids": sorted(str(value) for value in set(payload.targeting.geography_ids)),
            "languages": sorted(set(payload.targeting.languages)),
            "category_ids": sorted(str(value) for value in set(payload.targeting.category_ids)),
            "content_types": sorted(set(payload.targeting.content_types)),
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
                entity_type="advertising",
                entity_id=entity_id,
                before=before,
                after=after,
            )
        )
