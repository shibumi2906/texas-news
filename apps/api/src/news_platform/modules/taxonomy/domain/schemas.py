from pydantic import BaseModel, Field

from news_platform.modules.taxonomy.domain.models import TaxonomyStatus


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: TaxonomyStatus = TaxonomyStatus.ACTIVE
    sort_order: int = Field(default=0, ge=0)


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    status: TaxonomyStatus = TaxonomyStatus.ACTIVE
