from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from news_platform.infrastructure.database import Base
from news_platform.modules import models as platform_models  # noqa: F401
from news_platform.modules.content.domain.models import (
    ContentItem,
    ContentStatus,
    ContentType,
    ContentVersion,
    ContentVersionOrigin,
)
from news_platform.modules.editorial.api.router import router
from news_platform.modules.editorial.application.errors import PublicationBlockedError
from news_platform.modules.editorial.application.service import EditorialService
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.editorial.domain.policy import InvalidTransitionError, require_transition
from news_platform.modules.editorial.domain.schemas import EditorialEdit

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def database() -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[Any]]]:
    url = os.getenv("POSTGRES_TEST_URL")
    if not url:
        pytest.skip("POSTGRES_TEST_URL is required for PostgreSQL integration tests")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield engine, factory
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def create_content(
    session: AsyncSession,
    *,
    status: ContentStatus = ContentStatus.READY,
    upstream_status: ContentStatus = ContentStatus.RECEIVED,
) -> ContentItem:
    content = ContentItem(
        content_type=ContentType.ARTICLE,
        status=status,
        upstream_status=upstream_status,
        original_language="en",
        primary_language="en",
        title="Editorial story",
        metadata_={},
        seo={},
    )
    session.add(content)
    await session.flush()
    session.add(
        ContentVersion(
            content_item_id=content.id,
            version_number=1,
            source_revision=1,
            origin=ContentVersionOrigin.SOURCE,
            title=content.title,
            body="Source body",
            metadata_={},
        )
    )
    await session.flush()
    return content


async def test_transition_policy_is_explicit() -> None:
    require_transition(ContentStatus.READY, ContentStatus.PUBLISHED)
    require_transition(ContentStatus.PUBLISHED, ContentStatus.UNPUBLISHED)
    with pytest.raises(InvalidTransitionError):
        require_transition(ContentStatus.RECEIVED, ContentStatus.PUBLISHED)
    with pytest.raises(InvalidTransitionError):
        require_transition(ContentStatus.DELETED, ContentStatus.READY)


async def test_publish_unpublish_and_duplicate_publish_are_audited_once(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session)
        service = EditorialService(session)
        await service.publish(content.id, "editor:one", "approved")
        await service.publish(content.id, "editor:one", "duplicate")
        assert content.status is ContentStatus.PUBLISHED
        assert content.site_published_at is not None
    async with factory() as session, session.begin():
        await EditorialService(session).unpublish(content.id, "editor:two", "hold")
    async with factory() as session:
        stored = await session.get(ContentItem, content.id)
        actions = (await session.scalars(select(EditorialAuditLog.action))).all()
        assert stored is not None and stored.status is ContentStatus.UNPUBLISHED
        assert actions == ["publish", "unpublish"]
        assert await session.scalar(select(func.count()).select_from(ContentVersion)) == 1


@pytest.mark.parametrize("blocked", [ContentStatus.RETRACTED, ContentStatus.DELETED])
async def test_upstream_blocked_content_cannot_publish_or_restore(
    database: tuple[AsyncEngine, async_sessionmaker[Any]], blocked: ContentStatus
) -> None:
    _engine, factory = database
    async with factory() as session:
        async with session.begin():
            content = await create_content(
                session,
                status=ContentStatus.UNPUBLISHED,
                upstream_status=blocked,
            )
            content_id = content.id
        with pytest.raises(PublicationBlockedError):
            async with session.begin():
                await EditorialService(session).publish(content_id, "editor", "try publish")
        with pytest.raises(PublicationBlockedError):
            async with session.begin():
                await EditorialService(session).restore(content_id, "editor", "try restore")
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(EditorialAuditLog)) == 0


async def test_restore_from_editorial_unpublish_succeeds_while_upstream_is_active(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(
            session,
            status=ContentStatus.UNPUBLISHED,
            upstream_status=ContentStatus.RECEIVED,
        )
        restored = await EditorialService(session).restore(
            content.id, "editor", "source remains active"
        )
        assert restored.status is ContentStatus.PUBLISHED
        assert restored.upstream_status is ContentStatus.RECEIVED
    async with factory() as session:
        assert (await session.scalars(select(EditorialAuditLog.action))).all() == ["restore"]


async def test_schedule_reschedule_cancel_and_due_worker(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session)
        service = EditorialService(session)
        await service.schedule(content.id, "editor", datetime.now(UTC) + timedelta(hours=1))
        await service.schedule(content.id, "editor", datetime.now(UTC) + timedelta(hours=2))
        await service.cancel_schedule(content.id, "editor")
        assert content.status is ContentStatus.READY and content.scheduled_at is None
        await service.schedule(content.id, "editor", datetime.now(UTC) + timedelta(seconds=1))
        content.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
    async with factory() as session, session.begin():
        assert await EditorialService(session).publish_due(10) == 1
    async with factory() as session:
        stored = await session.get(ContentItem, content.id)
        actions = (await session.scalars(select(EditorialAuditLog.action))).all()
        assert stored is not None and stored.status is ContentStatus.PUBLISHED
        assert actions == ["schedule", "reschedule", "cancel_schedule", "schedule", "publish"]


async def test_scheduled_item_retracted_before_due_is_not_published(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session, status=ContentStatus.SCHEDULED)
        content.scheduled_at = datetime.now(UTC) - timedelta(seconds=1)
        content.upstream_status = ContentStatus.RETRACTED
    async with factory() as session, session.begin():
        assert await EditorialService(session).publish_due(10) == 0
    async with factory() as session:
        stored = await session.get(ContentItem, content.id)
        assert stored is not None and stored.status is ContentStatus.RETRACTED
        assert stored.scheduled_at is None
        assert (
            await session.scalar(
                select(EditorialAuditLog.action).where(EditorialAuditLog.entity_id == content.id)
            )
            == "cancel_schedule"
        )


@pytest.mark.parametrize("invalid_state", ["blank_title", "missing_version"])
async def test_due_worker_rechecks_required_publication_data(
    database: tuple[AsyncEngine, async_sessionmaker[Any]], invalid_state: str
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session, status=ContentStatus.SCHEDULED)
        content.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        content_id = content.id
        if invalid_state == "blank_title":
            content.title = " "
        else:
            await session.execute(
                delete(ContentVersion).where(ContentVersion.content_item_id == content_id)
            )

    async with factory() as session, session.begin():
        assert await EditorialService(session).publish_due(10) == 0

    async with factory() as session:
        stored = await session.get(ContentItem, content_id)
        assert stored is not None
        assert stored.status is ContentStatus.READY
        assert stored.scheduled_at is None
        assert (await session.scalars(select(EditorialAuditLog.action))).all() == [
            "cancel_schedule"
        ]


@pytest.mark.parametrize("racing_command", ["cancel", "reschedule"])
async def test_worker_does_not_publish_stale_due_state_after_locked_editorial_change(
    database: tuple[AsyncEngine, async_sessionmaker[Any]], racing_command: str
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session, status=ContentStatus.SCHEDULED)
        content.scheduled_at = datetime.now(UTC) - timedelta(minutes=1)
        content_id = content.id

    async def run_worker() -> int:
        async with factory() as worker_session, worker_session.begin():
            return await EditorialService(worker_session).publish_due(10)

    future_schedule = datetime.now(UTC) + timedelta(hours=1)
    async with factory() as session:
        async with session.begin():
            service = EditorialService(session)
            if racing_command == "cancel":
                await service.cancel_schedule(content_id, "editor", "race cancellation")
            else:
                await service.schedule(
                    content_id,
                    "editor",
                    future_schedule,
                    "race reschedule",
                )
            assert await run_worker() == 0

    async with factory() as session:
        stored = await session.get(ContentItem, content_id)
        actions = (await session.scalars(select(EditorialAuditLog.action))).all()
        assert stored is not None
        assert "publish" not in actions
        if racing_command == "cancel":
            assert stored.status is ContentStatus.READY
            assert stored.scheduled_at is None
            assert actions == ["cancel_schedule"]
        else:
            assert stored.status is ContentStatus.SCHEDULED
            assert stored.scheduled_at == future_schedule
            assert actions == ["reschedule"]


async def test_editorial_edit_creates_immutable_version_and_restore_rules(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session, status=ContentStatus.UNPUBLISHED)
        await EditorialService(session).edit(
            content.id,
            "editor:one",
            EditorialEdit(title="Edited title", body="Edited body", reason="copy edit"),
        )
    async with factory() as session, session.begin():
        restored = await EditorialService(session).restore(content.id, "editor:one", "restore")
        assert restored.status is ContentStatus.PUBLISHED
    async with factory() as session:
        versions = (
            await session.scalars(select(ContentVersion).order_by(ContentVersion.version_number))
        ).all()
        assert versions[0].title == "Editorial story"
        assert versions[0].origin == ContentVersionOrigin.SOURCE
        assert versions[1].title == "Edited title"
        assert versions[1].origin == ContentVersionOrigin.EDITORIAL
        assert versions[1].source_revision is None
        stored = await session.get(ContentItem, content.id)
        assert stored is not None and stored.has_editorial_override
        assert (await session.scalars(select(EditorialAuditLog.action))).all() == [
            "edit",
            "restore",
        ]


async def test_transaction_rollback_leaves_no_partial_edit(
    database: tuple[AsyncEngine, async_sessionmaker[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session)

    async def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(EditorialService, "_audit", fail_audit)
    async with factory() as session:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            async with session.begin():
                await EditorialService(session).edit(
                    content.id, "editor", EditorialEdit(title="Must rollback")
                )
    async with factory() as session:
        stored = await session.get(ContentItem, content.id)
        assert stored is not None and stored.title == "Editorial story"
        assert await session.scalar(select(func.count()).select_from(ContentVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(EditorialAuditLog)) == 0


@pytest.mark.parametrize("operation", ["publish", "schedule"])
async def test_transaction_rollback_leaves_no_partial_publication_or_schedule(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session)
        content_id = content.id

    async def fail_audit(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(EditorialService, "_audit", fail_audit)
    async with factory() as session:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            async with session.begin():
                service = EditorialService(session)
                if operation == "publish":
                    await service.publish(content_id, "editor", "must rollback")
                else:
                    await service.schedule(
                        content_id,
                        "editor",
                        datetime.now(UTC) + timedelta(hours=1),
                        "must rollback",
                    )

    async with factory() as session:
        stored = await session.get(ContentItem, content_id)
        assert stored is not None
        assert stored.status is ContentStatus.READY
        assert stored.scheduled_at is None
        assert stored.site_published_at is None
        assert await session.scalar(select(func.count()).select_from(ContentVersion)) == 1
        assert await session.scalar(select(func.count()).select_from(EditorialAuditLog)) == 0


async def test_admin_api_list_actor_and_validation(
    database: tuple[AsyncEngine, async_sessionmaker[Any]],
) -> None:
    _engine, factory = database
    async with factory() as session, session.begin():
        content = await create_content(session, status=ContentStatus.RECEIVED)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/v1/admin/content")).status_code == 401
        headers = {"X-Editorial-Actor": "editor:api"}
        listing = await client.get("/api/v1/admin/content?status=received", headers=headers)
        assert listing.status_code == 200 and listing.json()["total"] == 1
        ready = await client.post(
            f"/api/v1/admin/content/{content.id}/ready", headers=headers, json={}
        )
        assert ready.status_code == 200 and ready.json()["status"] == "ready"
        invalid_schedule = await client.post(
            f"/api/v1/admin/content/{content.id}/schedule",
            headers=headers,
            json={"scheduled_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
        )
        assert invalid_schedule.status_code == 422
        assert (
            await client.patch(f"/api/v1/admin/content/{content.id}", headers=headers, json={})
        ).status_code == 422
        assert (
            await client.patch(
                f"/api/v1/admin/content/{content.id}",
                headers=headers,
                json={"title": None},
            )
        ).status_code == 422
