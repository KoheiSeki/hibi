from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from hibi.db.base import Base
from hibi.modules.outbox.types import OUTBOX_STATUS_PENDING


class OutboxModel(Base):
    """`app.outbox_events` の 1 行。Capture とダイジェストが共有する、job の依頼の記録。

    依頼する側(Capture やダイジェストの repository)が、対象の行と同じ transaction で
    足し、relay が arq に投入してから配送済みにする。`aggregate_id` は対象によって
    指すテーブルが違うので、外部キーを持たない。対象を消すときは、依頼する側が
    自分の outbox の行も消す。
    """

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
