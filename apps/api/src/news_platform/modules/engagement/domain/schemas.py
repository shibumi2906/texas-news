from uuid import UUID

from pydantic import BaseModel, Field

from news_platform.modules.engagement.domain.models import EngagementMetric


class CounterIncrement(BaseModel):
    content_id: UUID
    metric: EngagementMetric
    amount: int = Field(default=1, ge=1, le=1_000_000)


class CounterReceipt(BaseModel):
    content_id: UUID
    metric: EngagementMetric
    value: int
    applied: bool
