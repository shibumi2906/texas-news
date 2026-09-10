from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StorySummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bullets: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=240)]], Field(min_length=2, max_length=4)
    ]


class AISourceReference(BaseModel):
    content_id: UUID
    title: str
    url: str
    canonical_url: str


class StorySummaryResponse(BaseModel):
    task: Literal["story_summary"] = "story_summary"
    language: str
    bullets: list[str]
    generated: bool = True
    fallback_used: bool
    cached: bool
    sources: list[AISourceReference]


class GroundedAnswerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)


class AIAnswerStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


AIAnswerTask = Literal["ai_search", "story_question", "trending_digest", "today_digest"]


class AIQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=500)
    language: str = Field(default="en", min_length=2, max_length=35)
    event_id: UUID
    anonymous_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class AIQuickBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    language: str = Field(default="en", min_length=2, max_length=35)
    event_id: UUID
    anonymous_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    session_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class AIAnswerMetadata(BaseModel):
    timezone: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    ranking_authoritative: bool = False


class AIAnswerResponse(BaseModel):
    task: AIAnswerTask
    answer: str
    status: AIAnswerStatus
    insufficient_evidence: bool
    generated: bool
    fallback_used: bool
    cached: bool
    sources: list[AISourceReference]
    metadata: AIAnswerMetadata
