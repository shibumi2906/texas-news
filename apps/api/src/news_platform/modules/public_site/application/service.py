from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import ContentType
from news_platform.modules.portals.domain.models import Portal
from news_platform.modules.public_site.domain.schemas import (
    PublicCategory,
    PublicCategoryPage,
    PublicCategorySection,
    PublicEntity,
    PublicGeography,
    PublicHomepage,
    PublicMedia,
    PublicPortal,
    PublicSource,
    PublicStory,
    PublicStorySummary,
)
from news_platform.modules.public_site.infrastructure.repository import (
    PublicContentRecord,
    PublicSiteRepository,
)
from news_platform.modules.taxonomy.domain.models import Category


class PublicNotFoundError(Exception):
    pass


class PublicSiteService:
    def __init__(self, session: AsyncSession, now: datetime | None = None) -> None:
        self.repository = PublicSiteRepository(session)
        self.now = now or datetime.now(UTC)

    async def homepage(self, portal_slug: str, language: str | None = None) -> PublicHomepage:
        portal = await self._portal(portal_slug)
        language = self._language(portal, language)
        categories = await self.repository.portal_categories(portal)
        latest, _ = await self.repository.list_content(portal, self.now, limit=6, language=language)
        sections = await self.repository.category_section_content(
            portal, categories, self.now, per_category=3, language=language
        )
        videos, _ = await self.repository.list_content(
            portal,
            self.now,
            content_types={ContentType.VIDEO},
            limit=4,
            language=language,
        )
        return PublicHomepage(
            portal=self._portal_view(portal, categories),
            language=language,
            canonical_url=self._localized_url(portal, language, ""),
            alternates=self._generic_alternates(portal, ""),
            hero=self._summary(portal, latest[0]) if latest else None,
            trending=[self._summary(portal, record) for record in latest[1:6]],
            category_sections=[
                PublicCategorySection(
                    category=PublicCategory(name=category.name, slug=category.slug),
                    items=[self._summary(portal, record) for record in sections[category.id]],
                )
                for category in categories
            ],
            video_highlights=[self._summary(portal, record) for record in videos],
        )

    async def category(
        self,
        portal_slug: str,
        category_slug: str,
        offset: int,
        limit: int,
        language: str | None = None,
    ) -> PublicCategoryPage:
        portal = await self._portal(portal_slug)
        language = self._language(portal, language)
        categories = await self.repository.portal_categories(portal)
        category = next((item for item in categories if item.slug == category_slug), None)
        if category is None:
            raise PublicNotFoundError("category not found")
        records, total = await self.repository.list_content(
            portal,
            self.now,
            category_id=category.id,
            offset=offset,
            limit=limit,
            language=language,
        )
        return PublicCategoryPage(
            portal=self._portal_view(portal, categories),
            language=language,
            category=PublicCategory(name=category.name, slug=category.slug),
            canonical_url=(
                f"{self._portal_base_url(portal)}"
                f"{'' if language == portal.default_language else f'/{language}'}"
                f"/{category.slug}"
            ),
            alternates=self._generic_alternates(portal, f"/{category.slug}"),
            items=[self._summary(portal, record) for record in records],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def story(
        self, portal_slug: str, story_slug: str, language: str | None = None
    ) -> PublicStory:
        portal = await self._portal(portal_slug)
        language = self._language(portal, language)
        categories = await self.repository.portal_categories(portal)
        record = await self.repository.get_story(portal, story_slug, self.now, language)
        if record is None:
            raise PublicNotFoundError("story not found")
        related: list[PublicContentRecord] = []
        if record.categories:
            related, _ = await self.repository.list_content(
                portal,
                self.now,
                category_id=record.categories[0].id,
                exclude_id=record.content.id,
                limit=3,
                language=language,
            )
        summary = self._summary(portal, record)
        return PublicStory(
            **summary.model_dump(),
            portal=self._portal_view(portal, categories),
            body=record.body,
            original_url=record.content.original_url,
            entities=[
                PublicEntity(
                    id=entity.id,
                    name=entity.canonical_name,
                    slug=entity.slug,
                    type=entity.type.value,
                )
                for entity in record.entities
            ],
            # Canonical SEO overrides belong to the canonical-language text. A
            # translated representation falls back to its localized content fields
            # rather than leaking canonical-language metadata into the alternate page.
            seo=record.content.seo if record.translation is None else {},
            related=[self._summary(portal, item) for item in related],
        )

    async def _portal(self, slug: str) -> Portal:
        portal = await self.repository.get_portal(slug)
        if portal is None:
            raise PublicNotFoundError("portal not found")
        return portal

    def _portal_view(self, portal: Portal, categories: list[Category]) -> PublicPortal:
        return PublicPortal(
            name=portal.name,
            slug=portal.slug,
            domain=portal.domain,
            timezone=portal.timezone,
            default_language=portal.default_language,
            supported_languages=portal.supported_languages,
            canonical_url=self._portal_base_url(portal),
            branding=portal.branding,
            categories=[
                PublicCategory(name=category.name, slug=category.slug) for category in categories
            ],
        )

    def portal_view(self, portal: Portal, categories: list[Category]) -> PublicPortal:
        return self._portal_view(portal, categories)

    def _summary(self, portal: Portal, record: PublicContentRecord) -> PublicStorySummary:
        content = record.content
        if content.site_published_at is None:
            raise RuntimeError("public eligibility invariant violated")
        prefix = "" if record.language == portal.default_language else f"/{record.language}"
        path = f"{prefix}/story/{content.slug}"
        base_url = self._portal_base_url(portal)
        alternates = {
            item_language: (
                f"{base_url}"
                f"{'' if item_language == portal.default_language else f'/{item_language}'}"
                f"/story/{content.slug}"
            )
            for item_language in portal.supported_languages
            if item_language in record.available_languages
        }
        return PublicStorySummary(
            id=content.id,
            slug=content.slug,
            url=path,
            canonical_url=f"{base_url}{path}",
            language=record.language,
            alternates=alternates,
            content_type=content.content_type,
            title=record.title,
            subtitle=record.subtitle,
            description=record.description,
            author=content.author,
            published_at=content.site_published_at,
            updated_at=record.representation_updated_at,
            source=(
                PublicSource(name=record.source.name, url=record.source.canonical_url)
                if record.source
                else None
            ),
            categories=[
                PublicCategory(name=category.name, slug=category.slug)
                for category in record.categories
            ],
            geography=[
                PublicGeography(
                    name=geography.name,
                    slug=geography.slug,
                    type=geography.type.value,
                )
                for geography in record.geographies
            ],
            media=[
                PublicMedia(
                    type=media.type.value,
                    url=media.storage_url or media.source_url or "",
                    thumbnail_url=(
                        str(media.metadata_.get("thumbnail_url"))
                        if media.metadata_.get("thumbnail_url")
                        else None
                    ),
                    width=media.width,
                    height=media.height,
                    attribution=media.attribution,
                )
                for media in record.media
            ],
        )

    def story_summary(self, portal: Portal, record: PublicContentRecord) -> PublicStorySummary:
        return self._summary(portal, record)

    @staticmethod
    def _language(portal: Portal, requested: str | None) -> str:
        language = (requested or portal.default_language).lower()
        if language not in portal.supported_languages:
            raise PublicNotFoundError("language not supported by portal")
        return language

    @staticmethod
    def _portal_base_url(portal: Portal) -> str:
        configured = portal.seo_settings.get("canonical_base_url")
        raw = str(configured) if configured else f"https://{portal.domain}"
        parsed = urlsplit(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return f"https://{portal.domain}"
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))

    @classmethod
    def _localized_url(cls, portal: Portal, language: str, path: str) -> str:
        prefix = "" if language == portal.default_language else f"/{language}"
        return f"{cls._portal_base_url(portal)}{prefix}{path}"

    @classmethod
    def _generic_alternates(cls, portal: Portal, path: str) -> dict[str, str]:
        return {
            language: cls._localized_url(portal, language, path)
            for language in portal.supported_languages
        }
