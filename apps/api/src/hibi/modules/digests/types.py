from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

DIGEST_AGGREGATE_TYPE = "digest_report"
DIGEST_GENERATION_REQUESTED = "digest_report.generation_requested"
DIGEST_KIND_DAILY = "daily"
DIGEST_KIND_WEEKLY = "weekly"
DIGEST_STATUS_PENDING = "pending"
DIGEST_STATUS_READY = "ready"
DIGEST_STATUS_FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DigestReport:
    """ダイジェストまたは週次レビュー 1 件を表すドメインの型。DB の行と、API の応答の間に置く。

    Attributes:
        id: 行の id。
        user_id: 所有者。
        kind: daily か weekly。
        period_start: ユーザーの暦日。daily はその日、weekly は週の月曜。
        timezone: 作ったときに使った IANA 名。
        status: pending、ready、failed のいずれか。
        content: ダイジェストの中身。ready のときだけ。pending と failed は None。
        content_version: 中身の形の版。daily-digest-v1 か weekly-review-v1。
        summary_model: 週次レビューの要約に使ったモデル名。daily は None。
        error_code: failed の理由。failed 以外は None。
        generated_at: ready になった時刻。ready 以外は None。
        created_at: 作成時刻。
        updated_at: 更新時刻。
    """

    id: UUID
    user_id: UUID
    kind: str
    period_start: date
    timezone: str
    status: str
    content: dict[str, object] | None
    content_version: str
    summary_model: str | None
    error_code: str | None
    generated_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ActiveUser:
    """ダイジェストを作る対象になる、直近に Capture がある利用者。

    Attributes:
        user_id: 利用者の id。
        timezone: プロフィールの IANA 名。プロフィールが無ければ UTC。
            名前の検証はしないので、不正な名前もそのまま入る。
    """

    user_id: UUID
    timezone: str
