from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from news_platform.modules.content.domain.models import ContentItem
from news_platform.modules.editorial.domain.models import EditorialAuditLog
from news_platform.modules.notifications.domain.models import (
    NotificationDelivery,
    NotificationMessage,
    NotificationSubscription,
)
from news_platform.modules.notifications.domain.schemas import (
    NotificationAdminOverview,
    NotificationMessageCreate,
    NotificationMessageResult,
    NotificationMessageView,
    SubscriptionResult,
    SubscriptionView,
    SubscriptionWrite,
)
from news_platform.modules.notifications.infrastructure.gateways import (
    DeliveryRequest,
    NotificationGateway,
    NotificationGatewayError,
    NotificationSender,
)
from news_platform.modules.portals.domain.models import Portal, PortalStatus
from news_platform.modules.public_site.infrastructure.repository import PublicSiteRepository
from news_platform.modules.users.application.service import AuthenticatedUser


class NotificationsNotFoundError(Exception):
    pass


class NotificationsDisabledError(Exception):
    pass


class NotificationService:
    def __init__(self, session: AsyncSession, *, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)

    async def list_subscriptions(self, auth: AuthenticatedUser) -> list[SubscriptionView]:
        self._enabled(auth.portal)
        items = list(
            (
                await self.session.scalars(
                    select(NotificationSubscription)
                    .where(
                        NotificationSubscription.portal_id == auth.portal.id,
                        NotificationSubscription.user_id == auth.user.id,
                    )
                    .order_by(NotificationSubscription.created_at, NotificationSubscription.id)
                )
            ).all()
        )
        return [self._subscription_view(item) for item in items]

    async def subscribe(
        self, auth: AuthenticatedUser, payload: SubscriptionWrite
    ) -> SubscriptionResult:
        self._enabled(auth.portal)
        if payload.channel == "email":
            destination = auth.user.email.lower()
            configuration: dict[str, Any] = {}
        else:
            assert payload.endpoint is not None and payload.p256dh and payload.auth
            destination = str(payload.endpoint)
            configuration = {"p256dh": payload.p256dh, "auth": payload.auth}
        digest = hashlib.sha256(destination.encode()).hexdigest()
        lock_key = (
            f"notification-subscription:{auth.portal.id}:{auth.user.id}:{payload.channel}:{digest}"
        )
        await self.session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(lock_key, 0)))
        )
        item = await self.session.scalar(
            select(NotificationSubscription).where(
                NotificationSubscription.portal_id == auth.portal.id,
                NotificationSubscription.user_id == auth.user.id,
                NotificationSubscription.channel == payload.channel,
                NotificationSubscription.destination_hash == digest,
            )
        )
        status = "created"
        if item is None:
            item = NotificationSubscription(
                portal_id=auth.portal.id,
                user_id=auth.user.id,
                channel=payload.channel,
                destination=destination,
                destination_hash=digest,
                configuration=configuration,
                enabled=payload.enabled,
            )
            self.session.add(item)
        else:
            status = (
                "unchanged"
                if item.configuration == configuration and item.enabled == payload.enabled
                else "updated"
            )
            item.destination = destination
            item.configuration = configuration
            item.enabled = payload.enabled
        await self.session.flush()
        return SubscriptionResult(status=status, subscription=self._subscription_view(item))

    async def remove_subscription(self, auth: AuthenticatedUser, subscription_id: UUID) -> None:
        self._enabled(auth.portal)
        item = await self.session.scalar(
            select(NotificationSubscription).where(
                NotificationSubscription.id == subscription_id,
                NotificationSubscription.portal_id == auth.portal.id,
                NotificationSubscription.user_id == auth.user.id,
            )
        )
        if item is None:
            raise NotificationsNotFoundError("subscription not found")
        item.enabled = False
        item.destination = "revoked"
        item.configuration = {}
        await self.session.flush()

    async def admin_overview(self, portal_slug: str) -> NotificationAdminOverview:
        portal = await self._portal(portal_slug, active_only=False)
        subscription_rows = (
            await self.session.execute(
                select(NotificationSubscription.channel, func.count())
                .where(
                    NotificationSubscription.portal_id == portal.id,
                    NotificationSubscription.enabled.is_(True),
                )
                .group_by(NotificationSubscription.channel)
            )
        ).all()
        subscriptions: dict[str, int] = {
            str(channel): int(count) for channel, count in subscription_rows
        }
        delivery_rows = (
            await self.session.execute(
                select(NotificationDelivery.status, func.count())
                .join(NotificationMessage)
                .where(NotificationMessage.portal_id == portal.id)
                .group_by(NotificationDelivery.status)
            )
        ).all()
        deliveries: dict[str, int] = {str(status): int(count) for status, count in delivery_rows}
        messages = list(
            (
                await self.session.scalars(
                    select(NotificationMessage)
                    .where(NotificationMessage.portal_id == portal.id)
                    .order_by(NotificationMessage.created_at.desc())
                    .limit(20)
                )
            ).all()
        )
        counts_by_message: dict[UUID, dict[str, int]] = {}
        message_ids = [message.id for message in messages]
        if message_ids:
            count_rows = (
                await self.session.execute(
                    select(
                        NotificationDelivery.message_id,
                        NotificationDelivery.status,
                        func.count(),
                    )
                    .where(NotificationDelivery.message_id.in_(message_ids))
                    .group_by(
                        NotificationDelivery.message_id,
                        NotificationDelivery.status,
                    )
                )
            ).all()
            for message_id, status, count in count_rows:
                counts_by_message.setdefault(message_id, {})[str(status)] = int(count)
        views: list[NotificationMessageView] = []
        for message in messages:
            counts = counts_by_message.get(message.id, {})
            views.append(
                NotificationMessageView(
                    id=message.id,
                    title=message.title,
                    channels=message.channels,
                    created_at=message.created_at,
                    pending=int(counts.get("pending", 0)),
                    sent=int(counts.get("sent", 0)),
                    failed=int(counts.get("failed", 0)),
                )
            )
        return NotificationAdminOverview(
            portal_slug=portal.slug,
            enabled=portal.feature_flags.get("notifications", False) is True,
            subscriptions=subscriptions,
            deliveries=deliveries,
            messages=views,
        )

    async def create_message(
        self, portal_slug: str, payload: NotificationMessageCreate, actor: str
    ) -> NotificationMessageResult:
        portal = await self._portal(portal_slug)
        self._enabled(portal)
        if payload.content_id is not None:
            content = await self.session.scalar(
                PublicSiteRepository(self.session)
                .eligible_statement(portal, self.now)
                .where(ContentItem.id == payload.content_id)
            )
            if content is None:
                raise NotificationsNotFoundError("public content not found")
        channels = sorted(set(payload.channels))
        message = NotificationMessage(
            portal_id=portal.id,
            content_id=payload.content_id,
            title=payload.title,
            body=payload.body,
            url=payload.url,
            channels=channels,
            created_by=actor,
        )
        self.session.add(message)
        await self.session.flush()
        subscriptions = list(
            (
                await self.session.scalars(
                    select(NotificationSubscription).where(
                        NotificationSubscription.portal_id == portal.id,
                        NotificationSubscription.enabled.is_(True),
                        NotificationSubscription.channel.in_(channels),
                    )
                )
            ).all()
        )
        for subscription in subscriptions:
            self.session.add(
                NotificationDelivery(
                    message_id=message.id,
                    subscription_id=subscription.id,
                    status="pending",
                    attempts=0,
                    next_attempt_at=self.now,
                )
            )
        await self.session.flush()
        self.session.add(
            EditorialAuditLog(
                actor=actor,
                action="notification_send",
                entity_type="notification",
                entity_id=message.id,
                before={},
                after={
                    "title": message.title,
                    "channels": channels,
                    "content_id": str(message.content_id) if message.content_id else None,
                    "queued": len(subscriptions),
                },
            )
        )
        return NotificationMessageResult(id=message.id, queued=len(subscriptions))

    async def _portal(self, slug: str, *, active_only: bool = True) -> Portal:
        statement = select(Portal).where(Portal.slug == slug)
        if active_only:
            statement = statement.where(Portal.status == PortalStatus.ACTIVE)
        portal = await self.session.scalar(statement)
        if portal is None:
            raise NotificationsNotFoundError("portal not found")
        return portal

    @staticmethod
    def _enabled(portal: Portal) -> None:
        if portal.feature_flags.get("notifications", False) is not True:
            raise NotificationsDisabledError

    @staticmethod
    def _subscription_view(item: NotificationSubscription) -> SubscriptionView:
        if not item.enabled:
            destination_hint = "disabled"
        elif item.channel == "email":
            local, _, domain = item.destination.partition("@")
            destination_hint = f"{local[:1]}***@{domain}"
        else:
            destination_hint = "web push endpoint"
        return SubscriptionView(
            id=item.id,
            channel=item.channel,
            destination_hint=destination_hint,
            enabled=item.enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


class NotificationDeliveryService:
    def __init__(
        self,
        session: AsyncSession,
        gateway: NotificationSender,
        *,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.gateway = gateway
        self.now = now or datetime.now(UTC)

    async def deliver_batch(self, limit: int) -> tuple[int, int]:
        deliveries = list(
            (
                await self.session.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.status == "pending",
                        NotificationDelivery.next_attempt_at <= self.now,
                    )
                    .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        subscription_ids = {delivery.subscription_id for delivery in deliveries}
        message_ids = {delivery.message_id for delivery in deliveries}
        subscriptions = (
            {
                item.id: item
                for item in (
                    await self.session.scalars(
                        select(NotificationSubscription).where(
                            NotificationSubscription.id.in_(subscription_ids)
                        )
                    )
                ).all()
            }
            if subscription_ids
            else {}
        )
        messages = (
            {
                item.id: item
                for item in (
                    await self.session.scalars(
                        select(NotificationMessage).where(NotificationMessage.id.in_(message_ids))
                    )
                ).all()
            }
            if message_ids
            else {}
        )
        sent = 0
        failed = 0
        for delivery in deliveries:
            subscription = subscriptions.get(delivery.subscription_id)
            message = messages.get(delivery.message_id)
            if subscription is None or message is None or not subscription.enabled:
                delivery.status = "failed"
                delivery.error_code = "subscription_unavailable"
                failed += 1
                continue
            delivery.attempts += 1
            try:
                await self.gateway.send(
                    subscription.channel,
                    DeliveryRequest(
                        delivery_id=delivery.id,
                        destination=subscription.destination,
                        configuration=subscription.configuration,
                        title=message.title,
                        body=message.body,
                        url=message.url,
                    ),
                )
            except NotificationGatewayError as exc:
                delivery.error_code = exc.code
                if delivery.attempts >= 5 or exc.code in {
                    "gateway_not_configured",
                    "unsupported_channel",
                }:
                    delivery.status = "failed"
                    failed += 1
                else:
                    delivery.next_attempt_at = self.now + timedelta(
                        minutes=2 ** (delivery.attempts - 1)
                    )
            else:
                delivery.status = "sent"
                delivery.sent_at = self.now
                delivery.error_code = None
                sent += 1
        await self.session.flush()
        return sent, failed


async def process_notifications_once(
    session_factory: async_sessionmaker[AsyncSession], gateway: NotificationGateway, batch_size: int
) -> tuple[int, int]:
    async with session_factory() as session, session.begin():
        return await NotificationDeliveryService(session, gateway).deliver_batch(batch_size)
