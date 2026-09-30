from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

IntegrationKind = Literal["ai_gateway", "email", "web_push"]


class SetupStatus(BaseModel):
    required: bool
    completed: bool


class InfrastructureStatus(BaseModel):
    database: bool
    redis: bool
    secrets_encryption: bool


class PublisherSettings(BaseModel):
    canonical_base_url: HttpUrl
    publisher_name: str = Field(min_length=2, max_length=255)
    legal_name: str = Field(min_length=2, max_length=255)
    newsroom_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=320)
    funding_disclosure: str = Field(min_length=2, max_length=1000)
    logo_url: HttpUrl | None = None


class IntegrationWrite(BaseModel):
    enabled: bool = False
    endpoint: HttpUrl | None = None
    provider_name: str | None = Field(default=None, max_length=100)
    secret: str | None = Field(default=None, min_length=8, max_length=4096)


class IntegrationView(BaseModel):
    kind: IntegrationKind
    enabled: bool
    endpoint: str | None
    provider_name: str | None
    secret_configured: bool
    secret_hint: str | None
    verified: bool
    last_error: str | None


class FeatureSettings(BaseModel):
    ai_search: bool = True
    ai_chat: bool = True
    advertising: bool = False
    notifications: bool = False
    community: bool = True
    recommendations: bool = True


class SetupOverview(BaseModel):
    portal_slug: str
    completed: bool
    infrastructure: InfrastructureStatus
    publisher: PublisherSettings | None
    features: FeatureSettings
    integrations: list[IntegrationView]


class ConnectionTestResult(BaseModel):
    ok: bool
    code: str
