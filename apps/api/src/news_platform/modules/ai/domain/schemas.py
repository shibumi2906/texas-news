from __future__ import annotations

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
