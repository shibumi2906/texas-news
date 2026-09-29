from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubscriptionWrite(StrictModel):
    channel: Literal["email", "web_push"]
    endpoint: HttpUrl | None = None
    p256dh: str | None = Field(default=None, min_length=16, max_length=512)
    auth: str | None = Field(default=None, min_length=8, max_length=256)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_channel(self) -> SubscriptionWrite:
        push_values = (self.endpoint, self.p256dh, self.auth)
        if self.channel == "web_push" and any(value is None for value in push_values):
            raise ValueError("web_push requires endpoint, p256dh and auth")
        if self.channel == "email" and any(value is not None for value in push_values):
            raise ValueError("email subscriptions use the authenticated account email")
        return self


class SubscriptionView(StrictModel):
    id: UUID
    channel: str
    destination_hint: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class SubscriptionResult(StrictModel):
    status: Literal["created", "updated", "unchanged"]
    subscription: SubscriptionView


class NotificationMessageCreate(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=1000)
    url: str = Field(min_length=1, max_length=2000, pattern=r"^/")
    content_id: UUID | None = None
    channels: list[Literal["email", "web_push"]] = Field(min_length=1, max_length=2)


class NotificationMessageView(StrictModel):
    id: UUID
    title: str
    channels: list[str]
    created_at: datetime
    pending: int
    sent: int
    failed: int


class NotificationAdminOverview(StrictModel):
    portal_slug: str
    enabled: bool
    subscriptions: dict[str, int]
    deliveries: dict[str, int]
    messages: list[NotificationMessageView]


class NotificationMessageResult(StrictModel):
    id: UUID
    queued: int
