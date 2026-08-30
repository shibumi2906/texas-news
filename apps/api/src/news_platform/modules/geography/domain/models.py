from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin, empty_object


class GeographyType(StrEnum):
    WORLD = "world"
    COUNTRY = "country"
    STATE_OR_PROVINCE = "state_or_province"
    METRO = "metro"
    CITY = "city"
    DISTRICT = "district"


class GeographyNode(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "geography_nodes"
    __table_args__ = (
        CheckConstraint(
            "type IN ('world', 'country', 'state_or_province', 'metro', 'city', 'district')",
            name="geography_type",
        ),
    )

    type: Mapped[GeographyType] = mapped_column(
        Enum(
            GeographyType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=False,
            name="geography_type",
            validate_strings=True,
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    parent_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("geography_nodes.id", ondelete="RESTRICT"), index=True
    )
    timezone: Mapped[str | None] = mapped_column(String(64))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )

    parent: Mapped[GeographyNode | None] = relationship(
        remote_side="GeographyNode.id", back_populates="children"
    )
    children: Mapped[list[GeographyNode]] = relationship(back_populates="parent")
