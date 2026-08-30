from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import TimestampMixin, UUIDPrimaryKeyMixin


class TaxonomyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


def taxonomy_status_type() -> Enum:
    return Enum(
        TaxonomyStatus,
        values_callable=lambda values: [value.value for value in values],
        native_enum=False,
        create_constraint=False,
        name="taxonomy_status",
        validate_strings=True,
    )


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="taxonomy_status"),)

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[TaxonomyStatus] = mapped_column(
        taxonomy_status_type(), default=TaxonomyStatus.ACTIVE, nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)


class Topic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "topics"
    __table_args__ = (CheckConstraint("status IN ('active', 'inactive')", name="taxonomy_status"),)

    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    status: Mapped[TaxonomyStatus] = mapped_column(
        taxonomy_status_type(), default=TaxonomyStatus.ACTIVE, nullable=False
    )
