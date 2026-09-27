from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from hibi.db.base import Base


class CaptureModel(Base):
    __tablename__ = "captures"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    raw_text: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(default="pending")
    idempotency_key: Mapped[str] = mapped_column()
    request_hash: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
