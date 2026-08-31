from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from news_platform.core.config import Settings
from news_platform.infrastructure.database import Base
from news_platform.modules import models as platform_models  # noqa: F401
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentGeography,
    ContentItem,
    ContentStatus,
    ContentTopic,
    ContentVersion,
    ContentVersionOrigin,
    Source,
)
from news_platform.modules.editorial.application.service import EditorialService
from news_platform.modules.editorial.domain.schemas import EditorialEdit
from news_platform.modules.geography.domain.models import GeographyNode
from news_platform.modules.ingestion.api.router import router
from news_platform.modules.ingestion.application.errors import RateLimitError
from news_platform.modules.ingestion.application.rate_limit import enforce_ingestion_rate_limit
from news_platform.modules.ingestion.application.security import sign_request
from news_platform.modules.ingestion.application.service import IngestionService
from news_platform.modules.ingestion.domain.models import (
    IncomingPackage,
    IncomingPackageVersion,
    IntegratorConnection,
)
from news_platform.modules.media.domain.models import MediaAsset
from news_platform.modules.taxonomy.domain.models import Category, Topic

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

INSTANCE_ID = UUID("11111111-1111-4111-8111-111111111111")
PACKAGE_ID = UUID("22222222-2222-4222-8222-222222222222")
TOPIC_ID = UUID("33333333-3333-4333-8333-333333333333")
SOURCE_ID = UUID("44444444-4444-4444-8444-444444444444")
MATERIAL_ID = UUID("55555555-5555-4555-8555-555555555555")
ACTIVE_SECRET = "phase-two-active-test-secret"
PREVIOUS_SECRET = "phase-two-previous-test-secret"


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, _key: str, _seconds: int) -> bool:
        return True


@pytest_asyncio.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[Any]]]:
    database_url = os.getenv("POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, session_factory
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[Any]]]:
    _engine, session_factory = database
    async with session_factory() as session, session.begin():
        session.add(
            IntegratorConnection(
                instance_id=INSTANCE_ID,
                name="Test Integrator",
                active_key_id="active-2026",
                active_secret=ACTIVE_SECRET,
                previous_key_id="previous-2026",
                previous_secret=PREVIOUS_SECRET,
            )
        )

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = session_factory
    app.state.redis = FakeRedis()
    app.state.settings = Settings(
        ingestion_clock_skew_seconds=300,
        ingestion_rate_limit=0,
    )
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client, session_factory


def package(
    version: int = 1,
    *,
    operation: str = "created",
    schema_version: str = "1.1",
    title: str | None = None,
    subtitle: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "package_id": str(PACKAGE_ID),
        "package_version": version,
        "instance_id": str(INSTANCE_ID),
        "event_id": str(uuid4()),
        "event_stage": "reported",
        "operation": operation,
        "revision_reason": (
            f"reason for {operation}"
            if operation in {"corrected", "retracted", "deleted"}
            else None
        ),
        "content": {
            "title": title or f"Package title v{version}",
            "lead": subtitle,
            "excerpt": f"Excerpt v{version}",
            "body": f"Body v{version}",
            "summary": None,
            "tags": ["texas"],
            "canonical_url": "https://example.com/texas-story",
            "language": "en",
            "direction": "ltr",
        },
        "facts": [],
        "entities": [
            {
                "type": "sports_team",
                "canonical_name": "Dallas Mavericks",
                "slug": "dallas-mavericks",
                "external_ids": {"league": "nba-dal"},
            }
        ],
        "taxonomy": ["Legacy Sports"],
        "regions": ["Texas"],
        "topics": [{"id": str(TOPIC_ID), "slug": "nba", "label": "NBA"}],
        "categories": [{"slug": "sports", "topic_id": str(TOPIC_ID), "label": "Sports"}],
        "geographies": [
            {
                "country": "United States",
                "country_code": "US",
                "state_or_region": "Texas",
                "city": "Dallas",
                "confidence": 0.95,
                "source": "ai",
                "source_material_id": str(MATERIAL_ID),
            }
        ],
        "sources": [
            {
                "source_id": str(SOURCE_ID),
                "source_material_id": str(MATERIAL_ID),
                "external_id": "source-story-1",
                "url": "https://example.com/source-story",
                "published_at": now,
                "fetched_at": now,
                "source_name": "Example News",
                "adapter_type": "rss",
                "author": "Reporter",
                "canonical_url": "https://example.com",
                "content_hash": "a" * 64,
            }
        ],
        "language_versions": {
            "es": {
                "title": "Título",
                "canonical_url": "https://example.com/es/texas-story",
                "language": "es",
            }
        },
        "media": [
            {
                "type": "image",
                "source_url": "https://example.com/image.jpg",
                "thumbnail_url": "https://example.com/thumb.jpg",
                "mime_type": "image/jpeg",
                "width": 1200,
                "height": 800,
                "duration": None,
                "external_id": "image-1",
                "provider": "origin",
                "source_material_id": str(MATERIAL_ID),
                "rights_hint": "link_only",
                "attribution": "Example News",
            }
        ],
        "ai_provenance": [
            {
                "operation_run_id": str(uuid4()),
                "operation": "extract_entities",
                "provider": "provider",
                "model": "model",
                "prompt_version_id": str(uuid4()),
                "release_id": None,
            }
        ],
        "rights": {"usage": "link_only"},
        "confidence": {"overall": 0.9},
        "warnings": [],
        "created_at": now,
        "updated_at": now,
    }
    if schema_version == "1.0":
        payload["topics"] = []
        payload["categories"] = []
        payload["geographies"] = []
        payload["media"] = []
        payload["ai_provenance"] = []
    return payload


def encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()


def headers(
    payload: dict[str, Any],
    body: bytes,
    *,
    secret: str = ACTIVE_SECRET,
    key_id: str = "active-2026",
    timestamp: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp or datetime.now(UTC).isoformat()
    return {
        "Idempotency-Key": f"{payload['package_id']}:{payload['package_version']}",
        "X-Integrator-Instance-Id": str(INSTANCE_ID),
        "X-Signing-Key-Id": key_id,
        "X-Timestamp": timestamp,
        "X-Signature": sign_request(secret, timestamp, body),
        "Content-Type": "application/json",
    }


async def post_package(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
    **header_options: Any,
) -> httpx.Response:
    body = encode(payload)
    return await client.post(
        "/internal/v1/ingestion/content",
        content=body,
        headers=headers(payload, body, **header_options),
    )


async def test_create_duplicate_and_complete_domain_mapping(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    payload = package()
    accepted = await post_package(http, payload)
    duplicate = await post_package(http, payload)

    assert accepted.status_code == 201
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["package_id"] == str(PACKAGE_ID)
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"

    async with session_factory() as session:
        incoming = await session.scalar(select(IncomingPackage))
        content = await session.scalar(select(ContentItem))
        assert incoming is not None and incoming.latest_version == 1
        assert content is not None and content.title == "Package title v1"
        assert content.metadata_["language_versions"]["es"]["language"] == "es"
        assert len(content.metadata_["ai_provenance"]) == 1
        for model in (
            IncomingPackageVersion,
            ContentVersion,
            Source,
            Category,
            Topic,
            GeographyNode,
            ContentCategory,
            ContentTopic,
            ContentEntity,
            ContentGeography,
            MediaAsset,
        ):
            assert await session.scalar(select(func.count()).select_from(model)) >= 1
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(ContentVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(MediaAsset)) == 1


async def test_out_of_order_versions_never_regress_current_state(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    assert (await post_package(http, package(1))).status_code == 201
    async with session_factory() as session, session.begin():
        content = await session.scalar(select(ContentItem))
        assert content is not None
        editorial = Category(name="Editorial Local", slug="editorial-local")
        session.add(editorial)
        await session.flush()
        session.add(ContentCategory(content_item_id=content.id, category_id=editorial.id))

    version_three = package(3, operation="updated")
    version_three["categories"] = [{"slug": "music", "topic_id": str(TOPIC_ID), "label": "Music"}]
    version_three["media"][0]["source_url"] = "https://example.com/version-three.jpg"
    assert (await post_package(http, version_three)).status_code == 201
    assert (await post_package(http, package(2, operation="updated"))).status_code == 201

    async with session_factory() as session:
        incoming = await session.scalar(select(IncomingPackage))
        content = await session.scalar(select(ContentItem))
        versions = (
            await session.scalars(
                select(IncomingPackageVersion).order_by(IncomingPackageVersion.package_version)
            )
        ).all()
        content_versions = (
            await session.scalars(select(ContentVersion).order_by(ContentVersion.version_number))
        ).all()
        assert incoming is not None and incoming.latest_version == 3
        assert content is not None and content.title == "Package title v3"
        assert [item.package_version for item in versions] == [1, 2, 3]
        assert [item.source_revision for item in content_versions] == [1, 3, 2]
        assert len({item.version_number for item in content_versions}) == 3
        category_slugs = set(
            await session.scalars(
                select(Category.slug)
                .join(ContentCategory, ContentCategory.category_id == Category.id)
                .where(ContentCategory.content_item_id == content.id)
            )
        )
        media_urls = set(
            await session.scalars(
                select(MediaAsset.source_url).where(MediaAsset.content_item_id == content.id)
            )
        )
        assert category_slugs == {"editorial-local", "music"}
        assert media_urls == {"https://example.com/version-three.jpg"}


async def test_correction_retraction_and_deletion_preserve_history(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    operations = ["created", "corrected", "retracted", "deleted"]
    expected_statuses = [
        ContentStatus.RECEIVED,
        ContentStatus.RECEIVED,
        ContentStatus.RETRACTED,
        ContentStatus.DELETED,
    ]
    for version, (operation, expected_status) in enumerate(
        zip(operations, expected_statuses, strict=True), start=1
    ):
        assert (await post_package(http, package(version, operation=operation))).status_code == 201
        async with session_factory() as session:
            current = await session.scalar(select(ContentItem))
            assert current is not None and current.status is expected_status

    async with session_factory() as session:
        content = await session.scalar(select(ContentItem))
        assert content is not None and content.status is ContentStatus.DELETED
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 4
        versions = (await session.scalars(select(ContentVersion))).all()
        assert len(versions) == 4
        assert {version.change_reason for version in versions if version.change_reason} == {
            "reason for corrected",
            "reason for retracted",
            "reason for deleted",
        }


async def test_schema_10_legacy_taxonomy_is_consumed_and_regions_preserved(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    response = await post_package(http, package(schema_version="1.0"))
    assert response.status_code == 201
    async with session_factory() as session:
        content = await session.scalar(select(ContentItem))
        assert content is not None
        assert content.metadata_["legacy_regions"] == ["Texas"]
        assert await session.scalar(select(func.count()).select_from(Topic)) == 1
        assert await session.scalar(select(func.count()).select_from(ContentTopic)) == 1


async def test_conflicting_immutable_version_returns_409(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    assert (await post_package(http, package())).status_code == 201
    conflict = package(title="Mutated immutable title")
    conflict["event_id"] = str(uuid4())
    response = await post_package(http, conflict)
    assert response.status_code == 409
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 1


async def test_security_failures_persist_nothing(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    payload = package()
    body = encode(payload)

    missing = await http.post("/internal/v1/ingestion/content", content=body)
    wrong_key = await http.post(
        "/internal/v1/ingestion/content",
        content=body,
        headers=headers(payload, body, key_id="retired-key"),
    )
    expired_at = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    expired = await http.post(
        "/internal/v1/ingestion/content",
        content=body,
        headers=headers(payload, body, timestamp=expired_at),
    )
    future_at = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    future = await http.post(
        "/internal/v1/ingestion/content",
        content=body,
        headers=headers(payload, body, timestamp=future_at),
    )
    invalid_headers = headers(payload, body)
    invalid_headers["X-Signature"] = "0" * 64
    invalid = await http.post(
        "/internal/v1/ingestion/content", content=body, headers=invalid_headers
    )
    signed_headers = headers(payload, body)
    tampered = await http.post(
        "/internal/v1/ingestion/content", content=body + b" ", headers=signed_headers
    )
    mismatch_headers = headers(payload, body)
    mismatch_headers["Idempotency-Key"] = f"{PACKAGE_ID}:99"
    mismatch_headers["X-Signature"] = sign_request(
        ACTIVE_SECRET, mismatch_headers["X-Timestamp"], body
    )
    mismatch = await http.post(
        "/internal/v1/ingestion/content", content=body, headers=mismatch_headers
    )

    assert [
        missing.status_code,
        wrong_key.status_code,
        expired.status_code,
        future.status_code,
        invalid.status_code,
        tampered.status_code,
        mismatch.status_code,
    ] == [401, 401, 401, 401, 401, 401, 422]
    for response in (wrong_key, expired, future, invalid, tampered):
        assert ACTIVE_SECRET not in response.text
        assert PREVIOUS_SECRET not in response.text
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 0


async def test_previous_key_is_accepted_and_unsupported_schema_is_not_persisted(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    accepted = await post_package(http, package(), secret=PREVIOUS_SECRET, key_id="previous-2026")
    assert accepted.status_code == 201

    async with session_factory() as session, session.begin():
        connection = await session.scalar(select(IntegratorConnection))
        assert connection is not None
        connection.previous_key_id = None
        connection.previous_secret = None
    retired = await post_package(
        http,
        package(2, operation="updated"),
        secret=PREVIOUS_SECRET,
        key_id="previous-2026",
    )
    assert retired.status_code == 401

    unsupported_payload = package(2, schema_version="2.0", operation="updated")
    unsupported = await post_package(http, unsupported_payload)
    assert unsupported.status_code == 422
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(IncomingPackageVersion)) == 1


async def test_rate_limit_is_keyed_by_integrator_instance() -> None:
    redis = FakeRedis()
    await enforce_ingestion_rate_limit(redis, INSTANCE_ID, limit=1, window_seconds=60)
    with pytest.raises(RateLimitError):
        await enforce_ingestion_rate_limit(redis, INSTANCE_ID, limit=1, window_seconds=60)


async def test_invalid_payload_and_transaction_failure_leave_no_partial_state(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http, session_factory = client
    invalid_payload = package()
    del invalid_payload["content"]["title"]
    assert (await post_package(http, invalid_payload)).status_code == 422

    async def fail_mapping(
        _self: IngestionService,
        _content_id: UUID,
        _envelope: Any,
    ) -> None:
        raise RuntimeError("simulated mapping failure")

    monkeypatch.setattr(IngestionService, "_map_media", fail_mapping)
    with pytest.raises(RuntimeError, match="simulated mapping failure"):
        await post_package(http, package())

    async with session_factory() as session:
        for model in (IncomingPackage, IncomingPackageVersion, ContentItem, ContentVersion, Source):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_upstream_update_preserves_phase_3_editorial_override(
    client: tuple[httpx.AsyncClient, async_sessionmaker[Any]],
) -> None:
    http, session_factory = client
    assert (await post_package(http, package(subtitle="Source subtitle v1"))).status_code == 201
    async with session_factory() as session, session.begin():
        content = await session.scalar(
            select(ContentItem).where(ContentItem.external_id == str(PACKAGE_ID))
        )
        assert content is not None
        content_id = content.id
        incoming = await session.scalar(
            select(IncomingPackage).where(IncomingPackage.package_id == PACKAGE_ID)
        )
        first_incoming_version = await session.scalar(
            select(IncomingPackageVersion).where(
                IncomingPackageVersion.package_id == PACKAGE_ID,
                IncomingPackageVersion.package_version == 1,
            )
        )
        assert incoming is not None and first_incoming_version is not None
        incoming_identity = (
            incoming.id,
            incoming.package_id,
            incoming.integrator_connection_id,
            incoming.content_item_id,
        )
        first_version_history = (
            first_incoming_version.id,
            first_incoming_version.body_sha256,
            deepcopy(first_incoming_version.payload),
            first_incoming_version.received_at,
        )
        await EditorialService(session).edit(
            content_id,
            "editor:override-test",
            EditorialEdit(
                title="Editorial title",
                subtitle="Editorial subtitle",
                description="Editorial description",
                body="Editorial body",
                reason="preserve this edit",
            ),
        )

    assert (
        await post_package(
            http,
            package(
                2,
                operation="updated",
                title="New upstream title",
                subtitle="Upstream subtitle v2",
            ),
        )
    ).status_code == 201
    async with session_factory() as session:
        stored = await session.get(ContentItem, content_id)
        versions = (
            await session.scalars(
                select(ContentVersion)
                .where(ContentVersion.content_item_id == content_id)
                .order_by(ContentVersion.version_number)
            )
        ).all()
        assert stored is not None
        assert stored.title == "Editorial title"
        assert stored.subtitle == "Editorial subtitle"
        assert stored.description == "Editorial description"
        assert stored.body == "Editorial body"
        assert stored.has_editorial_override
        assert [version.origin for version in versions] == [
            ContentVersionOrigin.SOURCE,
            ContentVersionOrigin.EDITORIAL,
            ContentVersionOrigin.SOURCE,
        ]
        assert [version.metadata_.get("subtitle") for version in versions] == [
            "Source subtitle v1",
            "Editorial subtitle",
            "Upstream subtitle v2",
        ]
        assert versions[-1].title == "New upstream title"
        incoming = await session.scalar(
            select(IncomingPackage).where(IncomingPackage.package_id == PACKAGE_ID)
        )
        incoming_versions = (
            await session.scalars(
                select(IncomingPackageVersion)
                .where(IncomingPackageVersion.package_id == PACKAGE_ID)
                .order_by(IncomingPackageVersion.package_version)
            )
        ).all()
        assert incoming is not None
        assert (
            incoming.id,
            incoming.package_id,
            incoming.integrator_connection_id,
            incoming.content_item_id,
        ) == incoming_identity
        assert incoming.latest_version == 2
        assert len(incoming_versions) == 2
        assert (
            incoming_versions[0].id,
            incoming_versions[0].body_sha256,
            incoming_versions[0].payload,
            incoming_versions[0].received_at,
        ) == first_version_history
        assert incoming_versions[1].payload["content"]["lead"] == "Upstream subtitle v2"
