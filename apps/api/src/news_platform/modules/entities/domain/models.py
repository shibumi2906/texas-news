from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Enum, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin, empty_list, empty_object


class EntityType(StrEnum):
    PERSON = "person"
    ORGANIZATION = "organization"
    SPORTS_TEAM = "sports_team"
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    GAME = "game"
    ARTIST = "artist"
    VENUE = "venue"
    EVENT = "event"
    BRAND = "brand"
    FRANCHISE = "franchise"
    LOCATION = "location"
    OTHER = "other"


class Entity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint(
            "type IN ('person', 'organization', 'sports_team', 'movie', 'tv_show', "
            "'game', 'artist', 'venue', 'event', 'brand', 'franchise', 'location', 'other')",
            name="entity_type",
        ),
        Index("ix_entities_aliases_gin", "aliases", postgresql_using="gin"),
        Index("ix_entities_external_ids_gin", "external_ids", postgresql_using="gin"),
    )

    type: Mapped[EntityType] = mapped_column(
        Enum(
            EntityType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="entity_type",
            validate_strings=True,
        ),
        nullable=False,
        index=True,
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, default=empty_list, nullable=False)
    external_ids: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=empty_object, nullable=False
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )
