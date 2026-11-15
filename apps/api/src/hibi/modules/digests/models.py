from datetime import date, datetime
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hibi.db.base import Base
from hibi.modules.digests.types import DIGEST_STATUS_PENDING


class DigestReportModel(Base):
    """ダイジェストと週次レビュー 1 件を表す、`app.digest_reports` の行。

    `(user_id, kind, period_start)` は unique で、同じ期間の行は 1 件にしかならない。
    行は先に `pending` で入れ、中身を作った処理だけが `ready` か `failed` にする。
    そのため `content` は `ready` のときだけ入り、`generated_at` もその時刻になる
    (DB の check で、`ready` と `content` の有無は一致させている)。

    Attributes:
        id: 行の id。アプリが発行する。
        user_id: 所有者。
        kind: daily か weekly。
        period_start: ユーザーの暦日。daily はその日、weekly は週の月曜。
        timezone: 作ったときに使った IANA 名。期間の日付の解釈に使う。
        status: pending、ready、failed のいずれか。
        content: ダイジェストの中身。ready のときだけ。pending と failed は None。
        content_version: 中身の形の版。daily-digest-v1 か weekly-review-v1。
        summary_model: 週次レビューの要約に使ったモデル名。daily は None。
        error_code: failed の理由。個人情報を含めない。failed 以外は None。
        generated_at: ready になった時刻。ready 以外は None。
        created_at: 作成時刻。
        updated_at: 更新時刻。止まった pending の検出に使う。
    """

    __tablename__ = "digest_reports"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column()
    period_start: Mapped[date] = mapped_column()
    timezone: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(default=DIGEST_STATUS_PENDING)
    content: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    content_version: Mapped[str] = mapped_column()
    summary_model: Mapped[str | None] = mapped_column()
    error_code: Mapped[str | None] = mapped_column()
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
