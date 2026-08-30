from typing import Any

from pydantic import BaseModel, Field

from news_platform.modules.entities.domain.models import EntityType


class EntityCreate(BaseModel):
    type: EntityType
    canonical_name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    aliases: list[str] = Field(default_factory=list)
    external_ids: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
