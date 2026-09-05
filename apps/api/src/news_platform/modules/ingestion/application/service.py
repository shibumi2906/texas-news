from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentGeographyRelationship,
    ContentItem,
    ContentStatus,
    ContentTopic,
    ContentType,
    ContentVersion,
    ContentVersionOrigin,
    Source,
)
from news_platform.modules.entities.domain.models import Entity, EntityType
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.ingestion.application.errors import (
    AuthenticationError,
    ImmutableConflictError,
    PayloadValidationError,
    UnsupportedSchemaError,
)
from news_platform.modules.ingestion.application.rate_limit import enforce_ingestion_rate_limit
from news_platform.modules.ingestion.application.security import (
    validate_timestamp,
    verification_secret,
    verify_signature,
)
from news_platform.modules.ingestion.domain.models import IncomingPackage, IncomingPackageVersion
from news_platform.modules.ingestion.domain.schemas import (
    SUPPORTED_SCHEMA_VERSIONS,
    CanonicalNewsPackageEnvelope,
    IncomingPackageReceipt,
    PackageGeography,
    PackageSourceRef,
)
from news_platform.modules.ingestion.infrastructure.repository import IngestionRepository
from news_platform.modules.media.domain.models import MediaAsset, MediaStatus, MediaType
from news_platform.modules.taxonomy.domain.models import Category, Topic


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = IngestionRepository(session)

    async def ingest(
        self,
        *,
        body: bytes,
        instance_id: UUID,
        signing_key_id: str,
        timestamp: str,
        signature: str,
        idempotency_key: str,
        clock_skew_seconds: int,
        redis_client: Any,
        rate_limit: int,
        rate_limit_window_seconds: int,
    ) -> IncomingPackageReceipt:
        connection = await self.repository.get_connection(instance_id)
        if connection is None or not connection.is_active:
            raise AuthenticationError("unknown or inactive Integrator instance")

        validate_timestamp(timestamp, clock_skew_seconds)
        secret = verification_secret(connection, signing_key_id)
        if secret is None:
            raise AuthenticationError("unknown or retired signing key")
        verify_signature(secret, timestamp, body, signature)

        await enforce_ingestion_rate_limit(
            redis_client,
            instance_id,
            limit=rate_limit,
            window_seconds=rate_limit_window_seconds,
        )

        envelope = self._validate_envelope(body)
        if envelope.instance_id != instance_id:
            raise AuthenticationError("Integrator instance header does not match package")
        expected_idempotency_key = f"{envelope.package_id}:{envelope.package_version}"
        if idempotency_key != expected_idempotency_key:
            raise PayloadValidationError("Idempotency-Key does not match package identity")

        body_hash = hashlib.sha256(body).hexdigest()
        existing = await self.repository.get_version(envelope.package_id, envelope.package_version)
        if existing is not None:
            if existing.body_sha256 != body_hash:
                raise ImmutableConflictError(
                    "package version already exists with different content"
                )
            return self._receipt(envelope, "duplicate", existing.received_at)

        event_version = await self.repository.get_version_by_event(envelope.event_id)
        if event_version is not None:
            raise ImmutableConflictError("event_id already belongs to another package version")

        incoming_package = await self.repository.get_package(envelope.package_id, lock=True)
        advances_latest = incoming_package is None or (
            envelope.package_version > incoming_package.latest_version
        )
        if incoming_package is None:
            incoming_package = await self.repository.add_package(
                IncomingPackage(
                    package_id=envelope.package_id,
                    integrator_connection_id=connection.id,
                    latest_version=envelope.package_version,
                )
            )
        elif incoming_package.integrator_connection_id != connection.id:
            raise ImmutableConflictError("package_id belongs to another Integrator connection")

        incoming_version = await self.repository.add_version(
            IncomingPackageVersion(
                incoming_package_id=incoming_package.id,
                package_id=envelope.package_id,
                package_version=envelope.package_version,
                schema_version=envelope.schema_version,
                instance_id=envelope.instance_id,
                event_id=envelope.event_id,
                operation=envelope.operation,
                revision_reason=envelope.revision_reason,
                body_sha256=body_hash,
                payload=envelope.model_dump(mode="json"),
            )
        )

        sources = [await self._upsert_source(source) for source in envelope.sources]
        content = await self._get_or_create_content(incoming_package, envelope, sources)
        await self._create_content_version(content, incoming_version, envelope)

        if advances_latest:
            await self._apply_current_mapping(content, envelope, sources)
            incoming_package.latest_version = envelope.package_version

        await self.session.flush()
        return self._receipt(envelope, "accepted", incoming_version.received_at)

    @staticmethod
    def _validate_envelope(body: bytes) -> CanonicalNewsPackageEnvelope:
        try:
            raw = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PayloadValidationError("request body is not valid JSON") from exc
        if not isinstance(raw, dict):
            raise PayloadValidationError("canonical package must be a JSON object")
        schema_version = raw.get("schema_version")
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise UnsupportedSchemaError("unsupported canonical package schema version")
        try:
            return CanonicalNewsPackageEnvelope.model_validate(raw)
        except ValidationError as exc:
            raise PayloadValidationError("invalid CanonicalNewsPackageEnvelope") from exc

    @staticmethod
    def _receipt(
        envelope: CanonicalNewsPackageEnvelope,
        status: str,
        received_at: datetime,
    ) -> IncomingPackageReceipt:
        return IncomingPackageReceipt(
            package_id=envelope.package_id,
            package_version=envelope.package_version,
            status=status,
            received_at=received_at,
        )

    async def _upsert_source(self, source: PackageSourceRef) -> Source:
        external_id = str(source.source_id)
        stored = await self.session.scalar(select(Source).where(Source.external_id == external_id))
        metadata = source.model_dump(mode="json")
        if stored is None:
            source_url = source.canonical_url or source.url
            name = source.source_name or urlparse(source_url).netloc or source.external_id
            stored = Source(
                external_id=external_id,
                name=name,
                slug=f"integrator-source-{source.source_id}",
                canonical_url=source_url,
                metadata_=metadata,
            )
            self.session.add(stored)
        else:
            stored.metadata_ = metadata
            if source.source_name:
                stored.name = source.source_name
            stored.canonical_url = source.canonical_url or source.url
        await self.session.flush()
        return stored

    async def _get_or_create_content(
        self,
        incoming_package: IncomingPackage,
        envelope: CanonicalNewsPackageEnvelope,
        sources: list[Source],
    ) -> ContentItem:
        content = None
        if incoming_package.content_item_id is not None:
            content = await self.session.scalar(
                select(ContentItem)
                .where(ContentItem.id == incoming_package.content_item_id)
                .with_for_update()
            )
        if content is None:
            content = await self.session.scalar(
                select(ContentItem)
                .where(ContentItem.external_id == str(envelope.package_id))
                .with_for_update()
            )
        if content is None:
            primary_source = envelope.sources[0] if envelope.sources else None
            content = ContentItem(
                external_id=str(envelope.package_id),
                slug=self._story_slug(envelope.content.title, envelope.package_id),
                content_type=ContentType.ARTICLE,
                status=self._content_status(envelope.operation),
                upstream_status=self._content_status(envelope.operation),
                source_id=sources[0].id if sources else None,
                original_url=envelope.content.canonical_url,
                original_language=envelope.content.language,
                primary_language=envelope.content.language,
                title=envelope.content.title,
                subtitle=envelope.content.lead,
                description=envelope.content.excerpt or envelope.content.summary,
                body=envelope.content.body,
                publication_time=primary_source.published_at if primary_source else None,
                original_publication_time=(primary_source.published_at if primary_source else None),
                first_seen_at=primary_source.fetched_at if primary_source else envelope.created_at,
                canonical_content_hash=(primary_source.content_hash if primary_source else None),
                author=primary_source.author if primary_source else None,
                metadata_={},
                seo={},
            )
            self.session.add(content)
            await self.session.flush()
        incoming_package.content_item_id = content.id
        return content

    async def _create_content_version(
        self,
        content: ContentItem,
        incoming_version: IncomingPackageVersion,
        envelope: CanonicalNewsPackageEnvelope,
    ) -> None:
        current_version = await self.session.scalar(
            select(func.coalesce(func.max(ContentVersion.version_number), 0)).where(
                ContentVersion.content_item_id == content.id
            )
        )
        next_version = (current_version or 0) + 1
        self.session.add(
            ContentVersion(
                content_item_id=content.id,
                version_number=next_version,
                source_revision=envelope.package_version,
                origin=ContentVersionOrigin.SOURCE,
                incoming_package_version_id=incoming_version.id,
                title=envelope.content.title,
                description=envelope.content.excerpt or envelope.content.summary,
                body=envelope.content.body,
                metadata_={
                    "subtitle": envelope.content.lead,
                    "package_id": str(envelope.package_id),
                    "schema_version": envelope.schema_version,
                    "operation": envelope.operation,
                    "event_id": str(envelope.event_id),
                    "language_versions": {
                        key: value.model_dump(mode="json")
                        for key, value in envelope.language_versions.items()
                    },
                    "ai_provenance": [
                        value.model_dump(mode="json") for value in envelope.ai_provenance
                    ],
                },
                change_reason=envelope.revision_reason,
            )
        )
        await self.session.flush()

    async def _apply_current_mapping(
        self,
        content: ContentItem,
        envelope: CanonicalNewsPackageEnvelope,
        sources: list[Source],
    ) -> None:
        await self._clear_previous_mappings(content)
        primary_source = envelope.sources[0] if envelope.sources else None
        upstream_status = self._content_status(envelope.operation)
        previous_effective_status = content.status
        content.upstream_status = upstream_status
        editorial_lifecycle = previous_effective_status in {
            ContentStatus.SCHEDULED,
            ContentStatus.PUBLISHED,
            ContentStatus.UNPUBLISHED,
            ContentStatus.ARCHIVED,
        }
        if upstream_status in {ContentStatus.RETRACTED, ContentStatus.DELETED}:
            content.status = upstream_status
            content.scheduled_at = None
        elif previous_effective_status in {ContentStatus.RETRACTED, ContentStatus.DELETED}:
            content.status = ContentStatus.READY
        elif not editorial_lifecycle:
            content.status = ContentStatus.RECEIVED
        content.source_id = sources[0].id if sources else None
        content.original_url = envelope.content.canonical_url
        content.original_language = envelope.content.language
        content.primary_language = envelope.content.language
        if not content.has_editorial_override:
            content.title = envelope.content.title
            content.subtitle = envelope.content.lead
            content.description = envelope.content.excerpt or envelope.content.summary
            content.body = envelope.content.body
        content.publication_time = primary_source.published_at if primary_source else None
        content.original_publication_time = primary_source.published_at if primary_source else None
        content.canonical_content_hash = primary_source.content_hash if primary_source else None
        content.author = primary_source.author if primary_source else None
        category_ids, topic_ids = await self._map_taxonomy(content.id, envelope)
        geography_ids = await self._map_geographies(content.id, envelope)
        entity_ids = await self._map_entities(content.id, envelope.entities)
        media_ids = await self._map_media(content.id, envelope)
        content.metadata_ = {
            "incoming_package": {
                "package_id": str(envelope.package_id),
                "package_version": envelope.package_version,
                "schema_version": envelope.schema_version,
                "operation": envelope.operation,
                "revision_reason": envelope.revision_reason,
            },
            "source_provenance": [source.model_dump(mode="json") for source in envelope.sources],
            "language_versions": {
                key: value.model_dump(mode="json")
                for key, value in envelope.language_versions.items()
            },
            "ai_provenance": [value.model_dump(mode="json") for value in envelope.ai_provenance],
            "legacy_taxonomy": envelope.taxonomy,
            "legacy_regions": envelope.regions,
            "facts": envelope.facts,
            "rights": envelope.rights,
            "warnings": envelope.warnings,
            "ingestion_associations": {
                "category_ids": [str(value) for value in category_ids],
                "topic_ids": [str(value) for value in topic_ids],
                "geography_ids": [str(value) for value in geography_ids],
                "entity_ids": [str(value) for value in entity_ids],
                "media_ids": [str(value) for value in media_ids],
            },
        }

    async def _clear_previous_mappings(self, content: ContentItem) -> None:
        tracked = content.metadata_.get("ingestion_associations", {})
        if not isinstance(tracked, dict):
            return
        mappings = (
            (ContentCategory, ContentCategory.category_id, "category_ids"),
            (ContentTopic, ContentTopic.topic_id, "topic_ids"),
            (ContentEntity, ContentEntity.entity_id, "entity_ids"),
            (ContentGeography, ContentGeography.geography_id, "geography_ids"),
            (MediaAsset, MediaAsset.id, "media_ids"),
        )
        for model, identity_column, key in mappings:
            raw_ids = tracked.get(key, [])
            if not isinstance(raw_ids, list):
                continue
            identities: list[UUID] = []
            for value in raw_ids:
                try:
                    identities.append(UUID(str(value)))
                except ValueError:
                    continue
            if identities:
                await self.session.execute(
                    delete(model).where(
                        model.content_item_id == content.id,
                        identity_column.in_(identities),
                    )
                )

    async def _map_taxonomy(
        self, content_id: UUID, envelope: CanonicalNewsPackageEnvelope
    ) -> tuple[list[UUID], list[UUID]]:
        category_ids: list[UUID] = []
        topic_ids: list[UUID] = []
        for category_data in envelope.categories:
            category = await self.session.scalar(
                select(Category).where(Category.slug == category_data.slug)
            )
            if category is None:
                category = Category(
                    name=category_data.label or self._label(category_data.slug),
                    slug=category_data.slug,
                )
                self.session.add(category)
                await self.session.flush()
            if await self.session.get(ContentCategory, (content_id, category.id)) is None:
                self.session.add(
                    ContentCategory(content_item_id=content_id, category_id=category.id)
                )
            category_ids.append(category.id)

        topics = list(envelope.topics)
        if not topics and not envelope.categories:
            for value in envelope.taxonomy:
                slug = self._slug(value)
                topic = await self.session.scalar(select(Topic).where(Topic.slug == slug))
                if topic is None:
                    topic = Topic(name=value, slug=slug)
                    self.session.add(topic)
                    await self.session.flush()
                if await self.session.get(ContentTopic, (content_id, topic.id)) is None:
                    self.session.add(ContentTopic(content_item_id=content_id, topic_id=topic.id))
                topic_ids.append(topic.id)

        for topic_data in topics:
            topic = await self.session.scalar(select(Topic).where(Topic.slug == topic_data.slug))
            if topic is None:
                topic = Topic(
                    name=topic_data.label or self._label(topic_data.slug),
                    slug=topic_data.slug,
                )
                self.session.add(topic)
                await self.session.flush()
            if await self.session.get(ContentTopic, (content_id, topic.id)) is None:
                self.session.add(ContentTopic(content_item_id=content_id, topic_id=topic.id))
            topic_ids.append(topic.id)
        return category_ids, topic_ids

    async def _map_geographies(
        self, content_id: UUID, envelope: CanonicalNewsPackageEnvelope
    ) -> list[UUID]:
        geography_ids: list[UUID] = []
        for index, geography in enumerate(envelope.geographies):
            node = await self._upsert_geography_hierarchy(geography)
            if node is None:
                continue
            relationship = (
                ContentGeographyRelationship.PRIMARY
                if index == 0
                else ContentGeographyRelationship.MENTIONED
            )
            key = (content_id, node.id, relationship)
            if await self.session.get(ContentGeography, key) is None:
                self.session.add(
                    ContentGeography(
                        content_item_id=content_id,
                        geography_id=node.id,
                        relationship_type=relationship,
                        confidence=(
                            Decimal(str(geography.confidence))
                            if geography.confidence is not None
                            else None
                        ),
                        source=geography.source,
                    )
                )
            geography_ids.append(node.id)
        return geography_ids

    async def _upsert_geography_hierarchy(
        self, geography: PackageGeography
    ) -> GeographyNode | None:
        parent: GeographyNode | None = None
        values: list[tuple[GeographyType, str | None]] = [
            (GeographyType.COUNTRY, geography.country or geography.country_code),
            (GeographyType.STATE_OR_PROVINCE, geography.state_or_region),
            (GeographyType.METRO, geography.metro),
            (GeographyType.CITY, geography.city),
            (GeographyType.DISTRICT, geography.district),
        ]
        path: list[str] = []
        for geography_type, name in values:
            if not name:
                continue
            path.append(name)
            statement = select(GeographyNode).where(
                GeographyNode.type == geography_type,
                func.lower(GeographyNode.name) == name.lower(),
            )
            if parent is not None:
                statement = statement.where(GeographyNode.parent_id == parent.id)
            if geography.country_code:
                statement = statement.where(GeographyNode.country_code == geography.country_code)
            node = await self.session.scalar(statement)
            if node is None:
                slug = self._slug("-".join(path))
                existing_slug = await self.session.scalar(
                    select(GeographyNode).where(GeographyNode.slug == slug)
                )
                if existing_slug is not None:
                    slug = f"{slug}-{hashlib.sha256('/'.join(path).encode()).hexdigest()[:8]}"
                node = GeographyNode(
                    type=geography_type,
                    name=name,
                    slug=slug,
                    country_code=geography.country_code,
                    parent_id=parent.id if parent else None,
                    metadata_={
                        "source": geography.source,
                        "state_or_region_code": geography.state_or_region_code,
                        "source_material_id": (
                            str(geography.source_material_id)
                            if geography.source_material_id
                            else None
                        ),
                    },
                )
                self.session.add(node)
                await self.session.flush()
            parent = node
        return parent

    async def _map_entities(self, content_id: UUID, entities: list[dict[str, Any]]) -> list[UUID]:
        entity_ids: list[UUID] = []
        for raw in entities:
            name = raw.get("canonical_name") or raw.get("name")
            entity_type = raw.get("type")
            if not isinstance(name, str) or entity_type not in {
                value.value for value in EntityType
            }:
                continue
            slug_value = raw.get("slug")
            slug = slug_value if isinstance(slug_value, str) else self._slug(name)
            entity = await self.session.scalar(select(Entity).where(Entity.slug == slug))
            if entity is None:
                external_ids = raw.get("external_ids", {})
                entity = Entity(
                    type=EntityType(entity_type),
                    canonical_name=name,
                    slug=slug,
                    aliases=raw.get("aliases", []),
                    external_ids=external_ids if isinstance(external_ids, dict) else {},
                    metadata_=raw,
                )
                self.session.add(entity)
                await self.session.flush()
            if await self.session.get(ContentEntity, (content_id, entity.id)) is None:
                self.session.add(
                    ContentEntity(
                        content_item_id=content_id,
                        entity_id=entity.id,
                        relationship_type="mentioned",
                        source="integrator",
                    )
                )
            entity_ids.append(entity.id)
        return entity_ids

    async def _map_media(
        self, content_id: UUID, envelope: CanonicalNewsPackageEnvelope
    ) -> list[UUID]:
        media_ids: list[UUID] = []
        for item in envelope.media:
            media_type = MediaType(item.type)
            existing = await self.session.scalar(
                select(MediaAsset).where(
                    MediaAsset.content_item_id == content_id,
                    MediaAsset.type == media_type,
                    MediaAsset.source_url == item.source_url,
                )
            )
            if existing is not None:
                media_ids.append(existing.id)
                continue
            asset = MediaAsset(
                content_item_id=content_id,
                type=media_type,
                source_url=item.source_url,
                mime_type=item.mime_type,
                width=item.width,
                height=item.height,
                duration=item.duration,
                attribution=item.attribution,
                metadata_={
                    "thumbnail_url": item.thumbnail_url,
                    "external_id": item.external_id,
                    "provider": item.provider,
                    "source_material_id": str(item.source_material_id),
                    "rights_hint": item.rights_hint,
                },
                status=MediaStatus.READY,
            )
            self.session.add(asset)
            await self.session.flush()
            media_ids.append(asset.id)
        return media_ids

    @staticmethod
    def _content_status(operation: str) -> ContentStatus:
        if operation == "retracted":
            return ContentStatus.RETRACTED
        if operation == "deleted":
            return ContentStatus.DELETED
        return ContentStatus.RECEIVED

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or hashlib.sha256(value.encode()).hexdigest()[:16]

    @staticmethod
    def _label(slug: str) -> str:
        return slug.replace("-", " ").strip().title()

    @classmethod
    def _story_slug(cls, title: str, package_id: UUID) -> str:
        title_slug = cls._slug(title)[:180].rstrip("-") or "story"
        return f"{title_slug}-{package_id.hex[:12]}"
