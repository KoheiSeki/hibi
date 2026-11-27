from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from hibi.modules.digests.constants import DigestKind, DigestStatus


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
    kind: DigestKind
    period_start: date
    timezone: str
    status: DigestStatus
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


@dataclass(frozen=True, slots=True)
class ListDigestReportsQuery:
    """ダイジェストと週次レビューの一覧の入力。

    検証は router が済ませた値を受け取る。service と repository は、値の範囲を
    もう一度確かめない。

    Attributes:
        user_id: 検証済みの所有者。この利用者の行だけを読む。
        kind: daily か weekly。None なら両方を読む。
        from_date: 期間の日付の下限で、その日を含む。None なら下限を付けない。
        limit: 返す最大件数。router が 1 以上 30 以下で検証済み。
    """

    user_id: UUID
    kind: DigestKind | None
    from_date: date | None
    limit: int
