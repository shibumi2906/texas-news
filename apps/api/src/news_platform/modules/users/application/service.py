from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.users.application.security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    new_token,
    token_digest,
    verify_password,
)
from news_platform.modules.users.domain.models import (
    AuthSession,
    User,
    UserIdentity,
    UserProfile,
    UserStatus,
)
from news_platform.modules.users.domain.schemas import (
    AuthView,
    ProfileUpdate,
    Registration,
    UserView,
)


class AuthenticationError(Exception):
    pass


class AccountConflictError(Exception):
    pass


class PortalNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    user: User
    profile: UserProfile
    portal: Portal
    session: AuthSession


@dataclass(frozen=True)
class SessionTokens:
    token: str
    csrf: str
    expires_at: datetime


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def user_view(user: User, profile: UserProfile) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        role=user.role,
        display_name=profile.display_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        preferred_language=profile.preferred_language,
        timezone=profile.timezone,
    )


class AuthService:
    def __init__(self, session: AsyncSession, session_hours: int = 168) -> None:
        self.session = session
        self.session_hours = session_hours

    async def portal(self, slug: str) -> Portal:
        portal = await self.session.scalar(
            select(Portal).where(Portal.slug == slug, Portal.status == PortalStatus.ACTIVE)
        )
        if portal is None:
            raise PortalNotFoundError
        return portal

    async def register(
        self, portal_slug: str, payload: Registration
    ) -> tuple[AuthView, SessionTokens]:
        portal = await self.portal(portal_slug)
        email = normalize_email(str(payload.email))
        if await self.session.scalar(select(User.id).where(User.email == email)) is not None:
            raise AccountConflictError
        user = User(email=email)
        self.session.add(user)
        await self.session.flush()
        self.session.add(
            UserIdentity(
                user_id=user.id,
                provider="email",
                subject=email,
                credential_hash=hash_password(payload.password),
                created_at=datetime.now(UTC),
            )
        )
        profile = UserProfile(
            user_id=user.id,
            display_name=payload.display_name,
            preferred_language=portal.default_language,
            timezone=portal.timezone,
        )
        self.session.add(profile)
        tokens = await self._new_session(user.id, portal.id)
        return AuthView(
            user=user_view(user, profile), csrf_token=tokens.csrf, expires_at=tokens.expires_at
        ), tokens

    async def login(
        self, portal_slug: str, email_value: str, password: str
    ) -> tuple[AuthView, SessionTokens]:
        portal = await self.portal(portal_slug)
        identity = await self.session.scalar(
            select(UserIdentity).where(
                UserIdentity.provider == "email",
                UserIdentity.subject == normalize_email(email_value),
            )
        )
        user = await self.session.get(User, identity.user_id) if identity else None
        valid = verify_password(
            password,
            identity.credential_hash
            if identity and identity.credential_hash
            else DUMMY_PASSWORD_HASH,
        )
        if user is None or not valid or user.status != UserStatus.ACTIVE:
            raise AuthenticationError
        profile = await self.session.get(UserProfile, user.id)
        if profile is None:
            raise AuthenticationError
        tokens = await self._new_session(user.id, portal.id)
        return AuthView(
            user=user_view(user, profile), csrf_token=tokens.csrf, expires_at=tokens.expires_at
        ), tokens

    async def _new_session(self, user_id: UUID, portal_id: UUID) -> SessionTokens:
        now = datetime.now(UTC)
        raw_token, csrf = new_token(), new_token()
        expires_at = now + timedelta(hours=self.session_hours)
        self.session.add(
            AuthSession(
                user_id=user_id,
                portal_id=portal_id,
                token_hash=token_digest(raw_token),
                csrf_hash=token_digest(csrf),
                created_at=now,
                expires_at=expires_at,
            )
        )
        await self.session.flush()
        return SessionTokens(raw_token, csrf, expires_at)

    async def authenticate(self, portal_slug: str, token: str | None) -> AuthenticatedUser:
        if not token:
            raise AuthenticationError
        now = datetime.now(UTC)
        row = (
            await self.session.execute(
                select(User, UserProfile, Portal, AuthSession)
                .join(UserProfile, UserProfile.user_id == User.id)
                .join(AuthSession, AuthSession.user_id == User.id)
                .join(Portal, Portal.id == AuthSession.portal_id)
                .where(
                    AuthSession.token_hash == token_digest(token),
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    User.status == UserStatus.ACTIVE,
                    Portal.slug == portal_slug,
                    Portal.status == PortalStatus.ACTIVE,
                )
            )
        ).one_or_none()
        if row is None:
            raise AuthenticationError
        return AuthenticatedUser(*row)

    async def update_profile(self, auth: AuthenticatedUser, payload: ProfileUpdate) -> UserView:
        if payload.preferred_language not in auth.portal.supported_languages:
            raise ValueError("language is not supported by this portal")
        if payload.timezone:
            try:
                ZoneInfo(payload.timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("unknown timezone") from exc
        auth.profile.display_name = " ".join(payload.display_name.split())
        auth.profile.bio = payload.bio.strip() if payload.bio else None
        auth.profile.avatar_url = str(payload.avatar_url) if payload.avatar_url else None
        auth.profile.preferred_language = payload.preferred_language
        auth.profile.timezone = payload.timezone
        await self.session.flush()
        return user_view(auth.user, auth.profile)
