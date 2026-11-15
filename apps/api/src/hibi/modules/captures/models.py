from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from hibi.db.base import Base
from hibi.modules.captures.types import (
    CAPTURE_STATUS_PENDING,
    OUTBOX_STATUS_PENDING,
)


class CaptureModel(Base):
    __tablename__ = "captures"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    raw_text: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(default=CAPTURE_STATUS_PENDING)
    idempotency_key: Mapped[str] = mapped_column()
    request_hash: Mapped[str] = mapped_column()
    processing_generation: Mapped[int] = mapped_column(default=1)
    category: Mapped[str | None] = mapped_column()
    route: Mapped[str | None] = mapped_column()
    urgency: Mapped[str | None] = mapped_column()
    urgency_score: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric)
    policy_version: Mapped[str | None] = mapped_column()
    question_version: Mapped[str | None] = mapped_column()
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clarification_text: Mapped[str | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutboxModel(Base):
    __tablename__ = "outbox_events"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    aggregate_type: Mapped[str] = mapped_column()
    aggregate_id: Mapped[UUID] = mapped_column()
    event_type: Mapped[str] = mapped_column()
    processing_generation: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default=OUTBOX_STATUS_PENDING)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaptureScenarioModel(Base):
    __tablename__ = "capture_scenarios"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    capture_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    route: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column()
    title: Mapped[str] = mapped_column()
    amount: Mapped[int | None] = mapped_column()
    remind_text: Mapped[str | None] = mapped_column()
    policy_version: Mapped[str] = mapped_column()
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaptureEmbeddingModel(Base):
    __tablename__ = "capture_embeddings"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    capture_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    content_text: Mapped[str] = mapped_column()
    content_hash: Mapped[str] = mapped_column()
    embedding: Mapped[list[float]] = mapped_column(Vector(8))
    embedding_model: Mapped[str] = mapped_column()
    embedding_dimensions: Mapped[int] = mapped_column()
    embedding_version: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
