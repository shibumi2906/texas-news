from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from news_platform.infrastructure.database import Base
from news_platform.modules.common import UUIDPrimaryKeyMixin, empty_object


class PromptDefinition(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_prompt_definitions"
    __table_args__ = (
        Index(
            "uq_ai_prompt_definitions_global_task",
            "task",
            unique=True,
            postgresql_where=text("portal_id IS NULL"),
        ),
        Index(
            "uq_ai_prompt_definitions_portal_task",
            "portal_id",
            "task",
            unique=True,
            postgresql_where=text("portal_id IS NOT NULL"),
        ),
    )

    task: Mapped[str] = mapped_column(String(120), nullable=False)
    portal_id: Mapped[UUID | None] = mapped_column(ForeignKey("portals.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PromptVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_definition_id", "version", name="uq_ai_prompt_version"),
        CheckConstraint("version > 0", name="version_positive"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="status"),
        Index("ix_ai_prompt_versions_definition_status", "prompt_definition_id", "status"),
    )

    prompt_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_prompt_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class AIResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_results"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_ai_results_cache_key"),
        Index("ix_ai_results_content", "content_id", "task"),
        Index("ix_ai_results_expires_at", "expires_at"),
    )

    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[str] = mapped_column(String(120), nullable=False)
    content_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(35), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=empty_object, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AIExecution(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_executions"
    __table_args__ = (
        CheckConstraint("latency_ms >= 0", name="latency_nonnegative"),
        CheckConstraint("input_tokens >= 0", name="input_tokens_nonnegative"),
        CheckConstraint("output_tokens >= 0", name="output_tokens_nonnegative"),
        CheckConstraint("estimated_cost >= 0", name="cost_nonnegative"),
        CheckConstraint("retry_count >= 0", name="retry_count_nonnegative"),
        Index("ix_ai_executions_task_created", "task", "created_at"),
        Index("ix_ai_executions_content", "content_id", "created_at"),
    )

    task: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    gateway: Mapped[str | None] = mapped_column(String(120))
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(80))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    content_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False
    )
    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=empty_object, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AITaskConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_task_configs"
    __table_args__ = (
        UniqueConstraint("portal_id", "task", name="uq_ai_task_configs_portal_task"),
        CheckConstraint("max_cost >= 0", name="max_cost_nonnegative"),
        CheckConstraint("max_input_tokens >= 128", name="max_input_tokens_minimum"),
        CheckConstraint("max_output_tokens >= 32", name="max_output_tokens_minimum"),
        CheckConstraint("max_retries BETWEEN 0 AND 5", name="max_retries_range"),
        CheckConstraint("timeout_seconds > 0 AND timeout_seconds <= 120", name="timeout_range"),
        Index("ix_ai_task_configs_portal", "portal_id"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    task: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_model: Mapped[str] = mapped_column(String(255), nullable=False)
    fallback_models: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    allowed_providers: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    max_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    max_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)


class AIExperiment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_experiments"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'paused')", name="status"),
        CheckConstraint("variant_b_percent BETWEEN 1 AND 99", name="variant_b_percent_range"),
        UniqueConstraint("portal_id", "task", name="uq_ai_experiments_portal_task"),
        Index("ix_ai_experiments_portal_status", "portal_id", "status"),
    )

    portal_id: Mapped[UUID] = mapped_column(
        ForeignKey("portals.id", ondelete="CASCADE"), nullable=False
    )
    task: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version_a_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    prompt_version_b_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_prompt_versions.id", ondelete="RESTRICT"), nullable=False
    )
    variant_b_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="paused", nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
