from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_phase_5_feeds import NOW, add_story, database, redis_client, seed_domain  # noqa: F401

from news_platform.modules.analytics.domain.models import BehaviorEvent
from news_platform.modules.community.api.router import router as community_router
from news_platform.modules.community.application.service import CommunityService
from news_platform.modules.community.domain.models import (
    Comment,
    CommentReport,
    Follow,
    Reaction,
    Save,
)
from news_platform.modules.content.domain.models import ContentEntity, ContentStatus
from news_platform.modules.engagement.domain.models import ContentEngagementCounter
from news_platform.modules.entities.domain.models import Entity, EntityType
from news_platform.modules.users.api.router import router as users_router
from news_platform.modules.users.application.security import token_digest, verify_password
from news_platform.modules.users.domain.models import AuthSession, User, UserIdentity

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def runtime(
    database: tuple[AsyncEngine, async_sessionmaker[AsyncSession]],  # noqa: F811
    redis_client: Redis,  # noqa: F811
) -> AsyncIterator[tuple[httpx.AsyncClient, async_sessionmaker[AsyncSession], dict[str, Any]]]:
    _engine, factory = database
    async with factory() as session, session.begin():
        domain = await seed_domain(session)
        story = await add_story(session, domain, 801, published_at=NOW - timedelta(hours=1))
        entity = Entity(
            type=EntityType.ARTIST,
            canonical_name="Austin Artist",
            slug="austin-artist-phase-8",
            aliases=[],
            external_ids={},
            metadata_={},
        )
        session.add(entity)
        await session.flush()
        session.add(ContentEntity(content_item_id=story.id, entity_id=entity.id))
        domain.update(story=story, entity=entity)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=lifespan)
    app.state.db_session_factory = factory
    app.state.redis = redis_client
    app.state.settings = SimpleNamespace(
        environment="test",
        auth_session_hours=168,
        auth_login_rate_limit=20,
        auth_rate_limit_window_seconds=60,
        auth_allowed_origins="http://test",
        community_rate_limit=50,
        community_rate_limit_window_seconds=60,
    )
    app.include_router(users_router)
    app.include_router(community_router)
    domain["app"] = app
    domain["redis"] = redis_client
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, factory, domain


async def register(
    client: httpx.AsyncClient,
    email: str = "reader@example.com",
    name: str = "Reader",
    portal: str = "texas",
) -> str:
    response = await client.post(
        f"/api/v1/portals/{portal}/auth/register",
        json={"email": email, "password": "correct horse battery", "display_name": name},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["csrf_token"])


def csrf(value: str) -> dict[str, str]:
    return {"X-CSRF-Token": value, "Origin": "http://test"}


async def test_authentication_hashes_credentials_and_revokes_sessions(runtime: Any) -> None:
    client, factory, _domain = runtime
    token = await register(client)
    raw_session = client.cookies.get("news_session")
    assert raw_session is not None
    payload = (await client.get("/api/v1/portals/texas/auth/me")).json()
    assert payload["email"] == "reader@example.com"
    assert "password" not in payload and "hash" not in payload

    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "reader@example.com"))
        assert user is not None
        identity = await session.scalar(select(UserIdentity).where(UserIdentity.user_id == user.id))
        assert identity is not None and identity.credential_hash is not None
        assert identity.credential_hash != "correct horse battery"
        assert verify_password("correct horse battery", identity.credential_hash)
        stored_session = await session.scalar(select(AuthSession))
        assert stored_session is not None
        assert stored_session.token_hash == token_digest(raw_session)
        assert stored_session.token_hash != raw_session
        stored_session_id = stored_session.id

    invalid = await client.post(
        "/api/v1/portals/texas/auth/login",
        json={"email": "reader@example.com", "password": "wrong-password-value"},
    )
    missing = await client.post(
        "/api/v1/portals/texas/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password-value"},
    )
    assert (invalid.status_code, invalid.json()) == (missing.status_code, missing.json())

    assert (await client.post("/api/v1/portals/texas/auth/logout")).status_code == 403
    assert (
        await client.post("/api/v1/portals/texas/auth/logout", headers=csrf(token))
    ).status_code == 200
    assert (await client.get("/api/v1/portals/texas/auth/me")).status_code == 401
    async with factory() as session:
        revoked = await session.get(AuthSession, stored_session_id)
        assert revoked is not None and revoked.revoked_at is not None
    client.cookies.set("news_session", raw_session, path="/api/v1/portals/")
    assert (await client.get("/api/v1/portals/texas/auth/me")).status_code == 401


async def test_sessions_are_rotated_and_csrf_is_bound_to_each_session(runtime: Any) -> None:
    client, _factory, domain = runtime
    client.cookies.set(
        "news_session", "attacker-fixed-token", domain="test.local", path="/api/v1/portals/"
    )
    csrf_a = await register(client, "session-a@example.com", "Session A")
    session_a = client.cookies.get("news_session")
    assert session_a is not None and session_a != "attacker-fixed-token"

    second_client = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    try:
        csrf_b = await register(second_client, "session-b@example.com", "Session B")
        session_b = second_client.cookies.get("news_session")
        assert session_b is not None and session_b != session_a
        profile = {
            "display_name": "Still Bound",
            "bio": None,
            "avatar_url": None,
            "preferred_language": "en",
            "timezone": "America/Chicago",
        }
        endpoint = "/api/v1/portals/texas/auth/profile"
        assert (await client.put(endpoint, headers=csrf(csrf_b), json=profile)).status_code == 403
        assert (
            await second_client.put(endpoint, headers=csrf(csrf_a), json=profile)
        ).status_code == 403
        assert (await client.put(endpoint, json=profile)).status_code == 403
        assert (
            await client.put(endpoint, headers=csrf("wrong-csrf-token"), json=profile)
        ).status_code == 403
        assert (
            await client.get(
                f"/api/v1/portals/texas/community/stories/{domain['story'].slug}/comments"
            )
        ).status_code == 200
        assert (await client.get("/api/v1/portals/oklahoma/auth/me")).status_code == 401
    finally:
        await second_client.aclose()


async def test_auth_inputs_reject_identity_and_role_injection(runtime: Any) -> None:
    client, _factory, _domain = runtime
    response = await client.post(
        "/api/v1/portals/texas/auth/register",
        json={
            "email": "injected@example.com",
            "password": "correct horse battery",
            "display_name": "Injected",
            "role": "admin",
            "session_id": str(uuid4()),
            "provider": "system",
        },
    )
    assert response.status_code == 422
    token = await register(client, "private@example.com", "Private")
    duplicate = await client.post(
        "/api/v1/portals/texas/auth/register",
        json={
            "email": "PRIVATE@example.com",
            "password": "correct horse battery",
            "display_name": "Duplicate",
        },
    )
    assert (duplicate.status_code, duplicate.json()) == (
        409,
        {"detail": {"code": "ACCOUNT_UNAVAILABLE"}},
    )
    assert "private@example.com" not in duplicate.text
    assert "hash" not in duplicate.text.lower()
    assert (
        await client.put(
            "/api/v1/portals/texas/auth/profile",
            headers=csrf(token),
            json={
                "display_name": "Private",
                "bio": None,
                "avatar_url": None,
                "preferred_language": "en",
                "timezone": "America/Chicago",
                "role": "admin",
            },
        )
    ).status_code == 422


async def test_expired_session_and_origin_csrf_are_rejected(runtime: Any) -> None:
    client, factory, _domain = runtime
    token = await register(client)
    forbidden = await client.put(
        "/api/v1/portals/texas/auth/profile",
        headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
        json={
            "display_name": "Changed",
            "bio": None,
            "avatar_url": None,
            "preferred_language": "en",
            "timezone": "America/Chicago",
        },
    )
    assert forbidden.status_code == 403
    async with factory() as session, session.begin():
        auth_session = await session.scalar(select(AuthSession))
        assert auth_session is not None
        auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert (await client.get("/api/v1/portals/texas/auth/me")).status_code == 401


async def test_authentication_and_community_rate_limits(runtime: Any) -> None:
    client, _factory, domain = runtime
    domain["app"].state.settings.auth_login_rate_limit = 1
    await domain["redis"].flushdb()
    first = await client.post(
        "/api/v1/portals/texas/auth/login",
        json={"email": "missing@example.com", "password": "wrong-password-value"},
    )
    second = await client.post(
        "/api/v1/portals/texas/auth/login",
        json={"email": "varied@example.com", "password": "another-wrong-value"},
    )
    assert first.status_code == 401
    assert second.status_code == 429
    portal_independent = await client.post(
        "/api/v1/portals/oklahoma/auth/login",
        json={"email": "varied@example.com", "password": "another-wrong-value"},
    )
    assert portal_independent.status_code == 401

    domain["app"].state.settings.auth_login_rate_limit = 20
    await domain["redis"].flushdb()
    token = await register(client, "limited@example.com", "Limited")
    domain["app"].state.settings.community_rate_limit = 1
    story = domain["story"]
    path = f"/api/v1/portals/texas/community/stories/{story.slug}/comments"
    allowed = await client.post(
        path,
        headers=csrf(token),
        json={"id": str(uuid4()), "body": "First"},
    )
    limited = await client.post(
        path,
        headers=csrf(token),
        json={"id": str(uuid4()), "body": "Second"},
    )
    assert allowed.status_code == 201
    assert limited.status_code == 429


async def test_comments_replies_reactions_reports_saves_and_follows(runtime: Any) -> None:
    client, factory, domain = runtime
    token = await register(client)
    story = domain["story"]
    comment_id = uuid4()
    path = f"/api/v1/portals/texas/community/stories/{story.slug}/comments"
    first, replay = await asyncio.gather(
        client.post(
            path,
            headers=csrf(token),
            json={"id": str(comment_id), "body": "Great local story"},
        ),
        client.post(
            path,
            headers=csrf(token),
            json={"id": str(comment_id), "body": "Great local story"},
        ),
    )
    assert sorted((first.status_code, replay.status_code)) == [200, 201]
    reply = await client.post(
        path,
        headers=csrf(token),
        json={"id": str(uuid4()), "body": "Agreed", "parent_id": str(comment_id)},
    )
    assert reply.status_code == 201
    assert len((await client.get(path)).json()["items"]) == 2
    page_one = (await client.get(path, params={"limit": 1})).json()
    page_two = (
        await client.get(path, params={"limit": 1, "cursor": page_one["next_cursor"]})
    ).json()
    assert [page_one["items"][0]["id"], page_two["items"][0]["id"]] == [
        str(comment_id),
        reply.json()["id"],
    ]

    reaction_path = f"/api/v1/portals/texas/community/stories/{story.slug}/reactions"
    assert (
        await client.put(reaction_path, headers=csrf(token), json={"reaction_type": "like"})
    ).json()["status"] == "created"
    assert (
        await client.put(reaction_path, headers=csrf(token), json={"reaction_type": "like"})
    ).json()["status"] == "unchanged"
    save_path = f"/api/v1/portals/texas/community/stories/{story.slug}/save"
    assert (await client.put(save_path, headers=csrf(token))).status_code == 200
    assert len((await client.get("/api/v1/portals/texas/community/me/saves")).json()) == 1

    report = await client.post(
        f"/api/v1/portals/texas/community/comments/{comment_id}/reports",
        headers=csrf(token),
        json={"reason": "other", "details": "Review this"},
    )
    duplicate = await client.post(
        f"/api/v1/portals/texas/community/comments/{comment_id}/reports",
        headers=csrf(token),
        json={"reason": "other", "details": "Review this"},
    )
    assert (report.status_code, duplicate.json()["status"]) == (201, "duplicate")

    follow_path = f"/api/v1/portals/texas/community/follows/entity/{domain['entity'].id}"
    assert (await client.put(follow_path, headers=csrf(token))).json()["active"] is True
    assert len((await client.get("/api/v1/portals/texas/community/me/follows")).json()) == 1

    async with factory() as session:
        counts = await session.get(ContentEngagementCounter, story.id)
        assert (
            counts is not None and counts.comments == 2 and counts.likes == 1 and counts.saves == 1
        )
        assert await session.scalar(select(func.count()).select_from(Comment)) == 2
        assert await session.scalar(select(func.count()).select_from(Reaction)) == 1
        assert await session.scalar(select(func.count()).select_from(Save)) == 1
        assert await session.scalar(select(func.count()).select_from(Follow)) == 1
        events = set((await session.scalars(select(BehaviorEvent.event_type))).all())
        assert {"comment", "like", "save", "follow"} <= events


async def test_ownership_moderation_visibility_and_concurrent_toggle(runtime: Any) -> None:
    client, factory, domain = runtime
    first_token = await register(client, "first@example.com", "First")
    story = domain["story"]
    comment_id = uuid4()
    comments_path = f"/api/v1/portals/texas/community/stories/{story.slug}/comments"
    await client.post(
        comments_path, headers=csrf(first_token), json={"id": str(comment_id), "body": "Owned"}
    )

    second_client = httpx.AsyncClient(transport=client._transport, base_url="http://test")
    try:
        second_token = await register(second_client, "second@example.com", "Second")
        denied = await second_client.put(
            f"/api/v1/portals/texas/community/comments/{comment_id}",
            headers=csrf(second_token),
            json={"body": "stolen"},
        )
        assert denied.status_code == 403
        denied_remove = await second_client.delete(
            f"/api/v1/portals/texas/community/comments/{comment_id}",
            headers=csrf(second_token),
        )
        assert denied_remove.status_code == 403
        moderation = await second_client.put(
            f"/api/v1/portals/texas/community/moderation/comments/{comment_id}?role=admin",
            headers=csrf(second_token),
            json={"status": "hidden"},
        )
        assert moderation.status_code == 403
        injected_header = await second_client.put(
            f"/api/v1/portals/texas/community/moderation/comments/{comment_id}",
            headers={**csrf(second_token), "X-User-Role": "admin"},
            json={"status": "hidden"},
        )
        assert injected_header.status_code == 403
        assert (
            await second_client.get("/api/v1/portals/oklahoma/community/me/follows")
        ).status_code == 401
        async with factory() as session, session.begin():
            second = await session.scalar(select(User).where(User.email == "second@example.com"))
            assert second is not None
            second.role = "editor"
        editor_denied = await second_client.put(
            f"/api/v1/portals/texas/community/moderation/comments/{comment_id}",
            headers=csrf(second_token),
            json={"status": "hidden"},
        )
        assert editor_denied.status_code == 403
        async with factory() as session, session.begin():
            second = await session.scalar(select(User).where(User.email == "second@example.com"))
            assert second is not None
            second.role = "moderator"
        hidden = await second_client.put(
            f"/api/v1/portals/texas/community/moderation/comments/{comment_id}",
            headers=csrf(second_token),
            json={"status": "hidden"},
        )
        assert hidden.status_code == 200
        assert (await client.get(comments_path)).json()["items"] == []
        assert (
            await client.post(
                f"/api/v1/portals/texas/community/comments/{comment_id}/reports",
                headers=csrf(first_token),
                json={"reason": "other", "details": None},
            )
        ).status_code == 404

        oklahoma_client = httpx.AsyncClient(transport=client._transport, base_url="http://test")
        try:
            oklahoma_token = await register(
                oklahoma_client, "oklahoma@example.com", "Oklahoma", "oklahoma"
            )
            cross_portal = await oklahoma_client.delete(
                f"/api/v1/portals/oklahoma/community/comments/{comment_id}",
                headers=csrf(oklahoma_token),
            )
            assert cross_portal.status_code == 404
        finally:
            await oklahoma_client.aclose()

        save_path = f"/api/v1/portals/texas/community/stories/{story.slug}/save"
        results = await asyncio.gather(
            second_client.put(save_path, headers=csrf(second_token)),
            second_client.put(save_path, headers=csrf(second_token)),
        )
        assert sorted(response.json()["status"] for response in results) == ["created", "unchanged"]
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(Save).where(Save.user_id == second.id)
                )
                == 1
            )
    finally:
        await second_client.aclose()

    async with factory() as session, session.begin():
        stored_story = await session.get(type(story), story.id)
        assert stored_story is not None
        stored_story.status = ContentStatus.UNPUBLISHED
    assert (await client.get(comments_path)).status_code == 404
    assert (
        await client.put(
            f"/api/v1/portals/texas/community/stories/{story.slug}/reactions",
            headers=csrf(first_token),
            json={"reaction_type": "like"},
        )
    ).status_code == 404


async def test_concurrent_uniqueness_non_negative_counters_and_rollback(
    runtime: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, factory, domain = runtime
    token = await register(client, "consistency@example.com", "Consistency")
    story = domain["story"]
    comments_path = f"/api/v1/portals/texas/community/stories/{story.slug}/comments"
    comment_id = uuid4()
    assert (
        await client.post(
            comments_path,
            headers=csrf(token),
            json={"id": str(comment_id), "body": "Consistency comment"},
        )
    ).status_code == 201

    reaction_path = f"/api/v1/portals/texas/community/stories/{story.slug}/reactions"
    reactions = await asyncio.gather(
        client.put(reaction_path, headers=csrf(token), json={"reaction_type": "like"}),
        client.put(reaction_path, headers=csrf(token), json={"reaction_type": "like"}),
    )
    assert sorted(response.json()["status"] for response in reactions) == ["created", "unchanged"]

    report_path = f"/api/v1/portals/texas/community/comments/{comment_id}/reports"
    reports = await asyncio.gather(
        client.post(report_path, headers=csrf(token), json={"reason": "other", "details": "x"}),
        client.post(report_path, headers=csrf(token), json={"reason": "other", "details": "x"}),
    )
    assert sorted(response.json()["status"] for response in reports) == ["created", "duplicate"]

    follow_path = f"/api/v1/portals/texas/community/follows/entity/{domain['entity'].id}"
    follows = await asyncio.gather(
        client.put(follow_path, headers=csrf(token)),
        client.put(follow_path, headers=csrf(token)),
    )
    assert sorted(response.json()["status"] for response in follows) == ["created", "unchanged"]

    removals = await asyncio.gather(
        client.delete(reaction_path, headers=csrf(token)),
        client.delete(reaction_path, headers=csrf(token)),
    )
    assert sorted(response.json()["status"] for response in removals) == ["removed", "unchanged"]
    assert (await client.delete(reaction_path, headers=csrf(token))).json()["status"] == "unchanged"
    assert (
        await client.delete(
            f"/api/v1/portals/texas/community/comments/{comment_id}", headers=csrf(token)
        )
    ).json()["status"] == "removed"
    assert (await client.get(comments_path)).json()["items"] == []

    async with factory() as session:
        user = await session.scalar(select(User).where(User.email == "consistency@example.com"))
        assert user is not None
        counts = await session.get(ContentEngagementCounter, story.id)
        assert counts is not None
        assert (counts.comments, counts.likes, counts.saves) == (0, 0, 0)
        assert await session.scalar(select(func.count()).select_from(Reaction)) == 0
        assert await session.scalar(select(func.count()).select_from(CommentReport)) == 1
        assert await session.scalar(select(func.count()).select_from(Follow)) == 1
        event_counts = dict(
            (
                await session.execute(
                    select(BehaviorEvent.event_type, func.count())
                    .where(BehaviorEvent.user_id == user.id)
                    .group_by(BehaviorEvent.event_type)
                )
            ).all()
        )
        assert event_counts == {"comment": 1, "follow": 1, "like": 1}

    def fail_after_side_effects(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("forced rollback")

    monkeypatch.setattr(CommunityService, "_event", fail_after_side_effects)
    save_path = f"/api/v1/portals/texas/community/stories/{story.slug}/save"
    with pytest.raises(RuntimeError, match="forced rollback"):
        await client.put(save_path, headers=csrf(token))
    async with factory() as session:
        counts = await session.get(ContentEngagementCounter, story.id)
        assert counts is not None and counts.saves == 0
        assert await session.scalar(select(func.count()).select_from(Save)) == 0
