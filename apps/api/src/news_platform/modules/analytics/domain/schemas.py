from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from news_platform.modules.analytics.domain.models import BehaviorEventType

CONTENT_EVENTS = {
    BehaviorEventType.IMPRESSION,
    BehaviorEventType.CLICK,
    BehaviorEventType.CONTENT_OPEN,
    BehaviorEventType.SCROLL,
    BehaviorEventType.VIDEO_START,
    BehaviorEventType.WATCH_TIME,
    BehaviorEventType.COMPLETION,
    BehaviorEventType.SHARE,
}
COMMON_PROPERTIES = {"surface", "position"}
EVENT_PROPERTIES = {
    BehaviorEventType.IMPRESSION: COMMON_PROPERTIES,
    BehaviorEventType.CLICK: COMMON_PROPERTIES,
    BehaviorEventType.CONTENT_OPEN: {"surface"},
    BehaviorEventType.SCROLL: {"percent"},
    BehaviorEventType.VIDEO_START: {"offset_seconds"},
    BehaviorEventType.WATCH_TIME: {"seconds"},
    BehaviorEventType.COMPLETION: set(),
    BehaviorEventType.SHARE: {"channel"},
    BehaviorEventType.SEARCH: {"result_count"},
}


class BehaviorEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    event_type: BehaviorEventType
    content_id: UUID | None = None
    entity_id: UUID | None = None
    geography_id: UUID | None = None
    timestamp: datetime
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_event(self) -> BehaviorEventBase:
        if self.event_type not in EVENT_PROPERTIES:
            raise ValueError("event type is server generated")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        if self.event_type in CONTENT_EVENTS and self.content_id is None:
            raise ValueError(f"content_id is required for {self.event_type.value}")
        if self.event_type is BehaviorEventType.SEARCH and self.content_id is not None:
            raise ValueError("search events must not include content_id")

        allowed = EVENT_PROPERTIES[self.event_type]
        unknown = set(self.properties) - allowed
        if unknown:
            raise ValueError("unsupported properties for event type")
        self._validate_properties()
        return self

    def _validate_properties(self) -> None:
        if self.event_type is BehaviorEventType.SCROLL and "percent" not in self.properties:
            raise ValueError("scroll requires percent")
        if "surface" in self.properties:
            value = self.properties["surface"]
            if not isinstance(value, str) or not 1 <= len(value) <= 64:
                raise ValueError("surface must be a string of 1 to 64 characters")
        if "channel" in self.properties:
            value = self.properties["channel"]
            if not isinstance(value, str) or not 1 <= len(value) <= 32:
                raise ValueError("channel must be a string of 1 to 32 characters")
        for name, minimum, maximum in (
            ("position", 0, 10_000),
            ("percent", 0, 100),
            ("offset_seconds", 0, 86_400),
            ("result_count", 0, 1_000_000),
        ):
            if name in self.properties:
                value = self.properties[name]
                if (
                    not isinstance(value, int)
                    or isinstance(value, bool)
                    or not minimum <= value <= maximum
                ):
                    raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
        if self.event_type is BehaviorEventType.WATCH_TIME:
            value = self.properties.get("seconds")
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 86_400:
                raise ValueError("watch_time requires integer seconds from 1 to 86400")


class BehaviorEventCreate(BehaviorEventBase):
    anonymous_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class AuthenticatedBehaviorEventCreate(BehaviorEventBase):
    """A future authenticated event; actor and session are derived from the cookie session."""


class BehaviorEventReceipt(BaseModel):
    id: UUID
    status: Literal["accepted", "duplicate"]


class AggregationBatchResult(BaseModel):
    processed: int
    ranking_updates: int


class InvalidationBatchResult(BaseModel):
    delivered: int
