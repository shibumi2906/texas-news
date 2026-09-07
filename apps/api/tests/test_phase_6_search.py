from __future__ import annotations

import asyncio
import base64
import json
import runpy
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from sqlalchemy import delete, select, text, update
from test_phase_2_ingestion import ACTIVE_SECRET, INSTANCE_ID, package, post_package
from test_phase_5_feeds import (  # noqa: F401
    NOW,
    add_story,
    database,
    redis_client,  # noqa: F401
    seed_domain,
)

from news_platform.core.config import Settings
from news_platform.modules.content.domain.models import (
    ContentCategory,
    ContentEntity,
    ContentItem,
    ContentStatus,
)
from news_platform.modules.editorial.api.router import router as editorial_router
from news_platform.modules.entities.domain.models import Entity, EntityType
from news_platform.modules.geography.domain.models import GeographyNode, GeographyType
from news_platform.modules.ingestion.api.router import router as ingestion_router
from news_platform.modules.ingestion.domain.models import IntegratorConnection
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.api.router import router as public_router
from news_platform.modules.search.api.router import router
from news_platform.modules.search.infrastructure.postgres import PostgresSearchBackend

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
BASE = "/api/v1/portals/texas/search"


@pytest_asyncio.fixture
async def search_db(database: Any) -> AsyncIterator[Any]:  # noqa: F811
    engine, factory = database
    revision = runpy.run_path(
        str(Path(__file__).parents[1] / "alembic/versions/0007_phase_6_search.py")
    )

    def install_search(connection: Any) -> None:
        # Start from the Phase 5 shape and exercise the actual migration, including
        # its generated representation and triggers, rather than copying its SQL.
        connection.execute(text("DROP TABLE search_generation"))
        connection.execute(text("ALTER TABLE content_items DROP COLUMN search_vector CASCADE"))
        connection.execute(text("DROP FUNCTION IF EXISTS advance_search_generation() CASCADE"))
        with Operations.context(MigrationContext.configure(connection)):
            revision["upgrade"]()

    async with engine.begin() as conn:
        await conn.run_sync(install_search)
    yield factory
    async with engine.begin() as conn:
        await conn.execute(text("DROP FUNCTION advance_search_generation() CASCADE"))


def client(factory: Any) -> httpx.AsyncClient:
    app = FastAPI()
    app.state.db_session_factory = factory
    app.include_router(router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def populate(factory: Any, count: int = 3) -> None:
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        for i in range(1, count + 1):
            await add_story(session, domain, i, published_at=NOW, title="Mavericks championship")


async def test_public_visibility_and_language(search_db: Any) -> None:
    async with search_db() as session, session.begin():
        domain = await seed_domain(session)
        await add_story(session, domain, 1, published_at=NOW, title="Mavericks")
        for i, status in enumerate([s for s in ContentStatus if s != ContentStatus.PUBLISHED], 2):
            await add_story(session, domain, i, published_at=NOW, title="Mavericks", status=status)
        for i, upstream in enumerate([ContentStatus.RETRACTED, ContentStatus.DELETED], 20):
            await add_story(
                session, domain, i, published_at=NOW, title="Mavericks", upstream_status=upstream
            )
        await add_story(
            session, domain, 30, published_at=NOW + timedelta(days=100), title="Mavericks"
        )
        item = await add_story(session, domain, 31, published_at=NOW, title="Mavericks")
        item.site_published_at = None
        await add_story(
            session, domain, 32, published_at=NOW, title="Mavericks", geography="oklahoma"
        )
        await add_story(session, domain, 33, published_at=NOW, title="Mavericks", language="es")
    async with client(search_db) as api:
        result = await api.get(BASE, params={"language": "en", "q": "Mavericks"})
        assert result.status_code == 200, result.text
        assert [i["slug"] for i in result.json()["items"]] == ["feed-story-1"]
        assert result.headers["cache-control"] == "no-store"
        result = await api.get(BASE, params={"language": "es", "q": "Mavericks"})
        assert [i["slug"] for i in result.json()["items"]] == ["feed-story-33"]
        assert (await api.get(BASE, params={"language": "fr"})).status_code == 404
        result = await api.get(BASE.replace("texas", "oklahoma"), params={"language": "en"})
        assert [i["slug"] for i in result.json()["items"]] == ["feed-story-32"]


@pytest.mark.parametrize("field", ["title", "subtitle", "description", "body"])
async def test_effective_fields_and_generated_index(search_db: Any, field: str) -> None:
    async with search_db() as session, session.begin():
        domain = await seed_domain(session)
        item = await add_story(session, domain, 1, published_at=NOW)
        setattr(item, field, "Astronauts dancing")
    async with client(search_db) as api:
        assert (
            len(
                (await api.get(BASE, params={"language": "en", "q": "astronaut dance"})).json()[
                    "items"
                ]
            )
            == 1
        )
        async with search_db() as session, session.begin():
            await session.execute(
                update(ContentItem).values(
                    {field: "Editorial replacement", "has_editorial_override": True}
                )
            )
        assert (await api.get(BASE, params={"language": "en", "q": "astronaut"})).json()[
            "items"
        ] == []
        assert (
            len((await api.get(BASE, params={"language": "en", "q": "editorial"})).json()["items"])
            == 1
        )


async def test_entity_filters_and_dates(search_db: Any) -> None:
    async with search_db() as session, session.begin():
        domain = await seed_domain(session)
        first = await add_story(
            session, domain, 1, published_at=NOW, title="Championship", category="sports"
        )
        await add_story(session, domain, 2, published_at=NOW, category="music", geography="dallas")
        entity = Entity(
            type=EntityType.SPORTS_TEAM,
            canonical_name="Dallas Mavericks",
            slug="dallas-mavericks",
            aliases=["Mavs"],
        )
        session.add(entity)
        await session.flush()
        session.add(ContentEntity(content_item_id=first.id, entity_id=entity.id))
    async with client(search_db) as api:
        for entity in ["Dallas Mavericks", "dallas-mavericks", "Mavs"]:
            response = await api.get(
                BASE,
                params={
                    "language": "en",
                    "entity": entity,
                    "category": "sports",
                    "geography": "texas",
                    "date_from": "2026-09-05",
                    "date_to": "2026-09-05",
                },
            )
            assert response.status_code == 200, response.text
            assert [i["slug"] for i in response.json()["items"]] == ["feed-story-1"]
        for filters in [
            {"entity": "unknown"},
            {"entity": "Mavs", "category": "music"},
            {"date_to": "2026-09-04"},
            {"date_from": "2026-09-06"},
            {"geography": "dallas", "category": "sports"},
        ]:
            assert (await api.get(BASE, params={"language": "en", **filters})).json()["items"] == []
        for filters in [{"category": "unknown"}, {"geography": "oklahoma"}]:
            assert (await api.get(BASE, params={"language": "en", **filters})).status_code == 404


async def test_rank_ties_traversal_and_context(search_db: Any) -> None:
    await populate(search_db, 5)
    async with client(search_db) as api:
        params = {"language": "en", "q": "championship", "limit": 2}
        first = (await api.get(BASE, params=params)).json()
        assert [i["slug"] for i in first["items"]] == ["feed-story-5", "feed-story-4"]
        seen = [i["id"] for i in first["items"]]
        cursor = first["next_cursor"]
        for change in [
            {"q": "Mavericks"},
            {"language": "es"},
            {"entity": "Mavs"},
            {"category": "music"},
            {"geography": "texas"},
            {"date_from": "2026-01-01"},
        ]:
            response = await api.get(BASE, params={**params, "cursor": cursor, **change})
            assert response.status_code == 400, response.text
        assert (
            await api.get(BASE.replace("texas", "oklahoma"), params={**params, "cursor": cursor})
        ).status_code == 400
        while cursor:
            response = await api.get(BASE, params={**params, "cursor": cursor})
            assert response.status_code == 200, response.text
            page = response.json()
            seen.extend(i["id"] for i in page["items"])
            cursor = page["next_cursor"]
        assert len(seen) == len(set(seen)) == 5
        async with search_db() as session, session.begin():
            await session.execute(
                update(ContentItem)
                .where(ContentItem.slug == "feed-story-1")
                .values(title="Championship championship championship")
            )
        response = await api.get(BASE, params={**params, "cursor": first["next_cursor"]})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_SEARCH_CURSOR"


async def test_weighted_rank_and_spanish(search_db: Any) -> None:
    async with search_db() as session, session.begin():
        domain = await seed_domain(session)
        await add_story(session, domain, 1, published_at=NOW, title="Dancing")
        item = await add_story(session, domain, 2, published_at=NOW)
        item.body = "Dancing"
        await add_story(
            session, domain, 3, published_at=NOW, language="es", title="Conciertos musicales"
        )
    async with client(search_db) as api:
        result = (await api.get(BASE, params={"language": "en", "q": "dance"})).json()
        assert [i["slug"] for i in result["items"]] == ["feed-story-1", "feed-story-2"]
        assert (
            len((await api.get(BASE, params={"language": "es", "q": "concierto"})).json()["items"])
            == 1
        )


@pytest.mark.parametrize(
    "params,status",
    [
        ({"q": "!!!"}, 200),
        ({"q": "the and"}, 200),
        ({"q": "' & | ! ("}, 200),
        ({"q": "x" * 201}, 422),
        ({"q": "a\x00b"}, 422),
        ({"limit": 51}, 422),
        ({"limit": 0}, 422),
        ({"date_from": "bad"}, 422),
        ({"date_from": "2026-09-06", "date_to": "2026-09-05"}, 422),
        ({"cursor": "garbage"}, 400),
    ],
)
async def test_input_validation(search_db: Any, params: dict[str, Any], status: int) -> None:
    await populate(search_db)
    async with client(search_db) as api:
        response = await api.get(BASE, params={"language": "en", **params})
        assert response.status_code == status, response.text
        if status == 200:
            assert response.json()["items"] == []


async def test_generation_lock_serializes_mutation(search_db: Any) -> None:
    await populate(search_db)
    started = asyncio.Event()

    async def mutate() -> None:
        async with search_db() as session, session.begin():
            started.set()
            await session.execute(
                update(ContentItem).values(upstream_status=ContentStatus.RETRACTED)
            )

    async with search_db() as session, session.begin():
        before = await PostgresSearchBackend(session).generation()
        task = asyncio.create_task(mutate())
        await started.wait()
        await asyncio.sleep(0.05)
        assert not task.done()
    await asyncio.wait_for(task, 5)
    async with search_db() as session, session.begin():
        assert await PostgresSearchBackend(session).generation() > before
    async with client(search_db) as api:
        assert (await api.get(BASE, params={"language": "en"})).json()["items"] == []


async def test_gin_index_plan(search_db: Any) -> None:
    await populate(search_db)
    async with search_db() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        plan = (
            (
                await session.execute(
                    text(
                        "EXPLAIN SELECT id FROM content_items WHERE search_vector "
                        "@@ plainto_tsquery('english', 'championship')"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert "ix_content_items_search_vector" in " ".join(plan)


@pytest_asyncio.fixture
async def runtime(search_db: Any, redis_client: Any) -> AsyncIterator[Any]:  # noqa: F811
    async with search_db() as session, session.begin():
        session.add(
            IntegratorConnection(
                instance_id=INSTANCE_ID,
                name="Search acceptance",
                active_key_id="active-2026",
                active_secret=ACTIVE_SECRET,
            )
        )
    app = FastAPI()
    app.state.db_session_factory = search_db
    app.state.redis = redis_client
    app.state.settings = Settings(ingestion_rate_limit=0)
    for route in (router, editorial_router, ingestion_router, public_router):
        app.include_router(route)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as api:
        yield api, search_db


async def command(api: httpx.AsyncClient, content_id: str, action: str) -> httpx.Response:
    return await api.post(
        f"/api/v1/admin/content/{content_id}/{action}",
        headers={"X-Editorial-Actor": "editor:search-review"},
        json={},
    )


async def published_source(api: httpx.AsyncClient, factory: Any) -> str:
    response = await post_package(api, package(title="Originalquartz", subtitle="Originalsaffron"))
    assert response.status_code == 201, response.text
    async with factory() as session, session.begin():
        item = await session.scalar(select(ContentItem))
        identity = str(item.id)
        texas = await session.scalar(
            select(GeographyNode).where(
                GeographyNode.type == GeographyType.STATE_OR_PROVINCE, GeographyNode.name == "Texas"
            )
        )
        assert texas is not None
        session.add(
            Portal(
                slug="texas",
                name="Texas",
                domain="texas.example",
                status=PortalStatus.ACTIVE,
                primary_geography_id=texas.id,
                default_language="en",
                supported_languages=["en"],
                timezone="America/Chicago",
                branding={},
                category_settings={"enabled": ["sports"]},
                ranking_settings={},
                ai_settings={},
                advertising_settings={},
                seo_settings={},
                feature_flags={},
            )
        )
    for action in ("ready", "publish"):
        response = await command(api, identity, action)
        assert response.status_code == 200, response.text
    return identity


async def hits(api: httpx.AsyncClient, word: str) -> list[Any]:
    response = await api.get(BASE, params={"language": "en", "q": word})
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_ingest_edit_upstream_update_preserves_all_effective_search_text(
    runtime: Any,
) -> None:
    api, factory = runtime
    identity = await published_source(api, factory)
    assert len(await hits(api, "Originalquartz")) == 1
    editorial = dict(
        title="Editorialquartz",
        subtitle="Editorialsaffron",
        description="Editorialnebula",
        body="Editorialmarigold",
    )
    response = await api.patch(
        f"/api/v1/admin/content/{identity}",
        headers={"X-Editorial-Actor": "editor:search-review"},
        json=editorial,
    )
    assert response.status_code == 200, response.text
    # Immediately after edit: no reindex job or cache operation is performed.
    for word in editorial.values():
        assert len(await hits(api, word)) == 1
    assert await hits(api, "Originalquartz") == []
    newer = package(2, operation="updated", title="Upstreamquartz", subtitle="Upstreamsaffron")
    newer["content"].update(excerpt="Upstreamnebula", body="Upstreammarigold")
    assert (await post_package(api, newer)).status_code == 201
    for word in editorial.values():
        result = await hits(api, word)
        assert len(result) == 1
        assert {field: result[0][field] for field in ("title", "subtitle", "description")} == {
            field: editorial[field] for field in ("title", "subtitle", "description")
        }
        # Search intentionally returns summaries; body is exposed by the story read model.
        story = await api.get(f"/api/v1/portals/texas/stories/{result[0]['slug']}")
        assert story.status_code == 200
        assert all(story.json()[field] == value for field, value in editorial.items())
    for word in ("Upstreamquartz", "Upstreamsaffron", "Upstreamnebula", "Upstreammarigold"):
        assert await hits(api, word) == []
    async with factory() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        for word in editorial.values():
            result = await session.execute(
                text(
                    "SELECT id FROM content_items WHERE search_vector "
                    "@@ plainto_tsquery('english', :word)"
                ),
                {"word": word},
            )
            assert [str(row[0]) for row in result] == [identity]


@pytest.mark.parametrize("action", ["unpublish", "retracted", "deleted"])
async def test_runtime_removal_and_allowed_restore(runtime: Any, action: str) -> None:
    api, factory = runtime
    identity = await published_source(api, factory)
    assert len(await hits(api, "Originalquartz")) == 1
    if action == "unpublish":
        assert (await command(api, identity, action)).status_code == 200
    else:
        assert (
            await post_package(api, package(2, operation=action, title="Originalquartz"))
        ).status_code == 201
    assert await hits(api, "Originalquartz") == []
    async with factory() as session:
        assert (
            await session.scalar(
                text(
                    "SELECT search_vector @@ plainto_tsquery('english', "
                    "'Originalquartz') FROM content_items"
                )
            )
            is True
        )
    if action == "unpublish":
        for recovery in ("restore", "publish"):
            assert (await command(api, identity, recovery)).status_code == 200
            assert len(await hits(api, "Originalquartz")) == 1
            assert (await command(api, identity, "unpublish")).status_code == 200
    else:
        assert (await command(api, identity, "restore")).status_code == 409
        assert await hits(api, "Originalquartz") == []


async def test_association_change_invalidates_cursor_and_restart(search_db: Any) -> None:
    await populate(search_db, 4)
    async with client(search_db) as api:
        params = {"language": "en", "q": "championship", "category": "sports", "limit": 2}
        first = (await api.get(BASE, params=params)).json()
        async with search_db() as session, session.begin():
            await session.execute(
                delete(ContentCategory).where(
                    ContentCategory.content_item_id == first["items"][0]["id"]
                )
            )
        stale = await api.get(BASE, params={**params, "cursor": first["next_cursor"]})
        assert stale.status_code == 400
        assert stale.json()["detail"]["code"] == "INVALID_SEARCH_CURSOR"
        page = (await api.get(BASE, params=params)).json()
        identities = [i["id"] for i in page["items"]]
        while page["next_cursor"]:
            page = (await api.get(BASE, params={**params, "cursor": page["next_cursor"]})).json()
            identities.extend(i["id"] for i in page["items"])
        assert len(identities) == len(set(identities)) == 3
        assert first["items"][0]["id"] not in identities


async def test_cursor_normalization_and_typed_malformed_context(search_db: Any) -> None:
    await populate(search_db, 4)
    async with client(search_db) as api:
        params = {"language": "en", "q": "  Mavericks   championship  ", "limit": 1}
        first = (await api.get(BASE, params=params)).json()
        cursor = first["next_cursor"]
        response = await api.get(
            BASE, params={**params, "q": "Mavericks championship", "cursor": cursor}
        )
        assert response.status_code == 200
        assert response.json()["items"][0]["id"] != first["items"][0]["id"]
        invalid = ["!!!", base64.urlsafe_b64encode(b"[]").decode()]
        payload = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        for key, value in [
            ("version", 99),
            ("score", "NaN"),
            ("score", "Infinity"),
            ("snapshot_at", "2999-01-01T00:00:00Z"),
        ]:
            invalid.append(
                base64.urlsafe_b64encode(json.dumps({**payload, key: value}).encode()).decode()
            )
        for value in invalid:
            response = await api.get(BASE, params={**params, "cursor": value})
            assert response.status_code == 400, response.text
            assert response.json()["detail"]["code"] == "INVALID_SEARCH_CURSOR"
        response = await api.get(BASE, params={**params, "cursor": cursor, "date_to": "2026-09-30"})
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "INVALID_SEARCH_CURSOR"
