from sqlalchemy import BigInteger, CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base


class SearchGeneration(Base):
    __tablename__ = "search_generation"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
