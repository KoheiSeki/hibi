from datetime import date, datetime
from uuid import UUID

from hibi.core.models import ApiModel
from hibi.modules.digests.constants import (
    DigestKind,
    DigestStatus,
)


class DigestReportResponse(ApiModel):
    """朝のダイジェスト、または週次レビュー 1 件。

    kind は daily か weekly。periodStart は、利用者の timezone での暦日で、daily は
    その日、weekly は対象の週の月曜。timezone は、作ったときに使った IANA 名。

    status は pending、ready、failed のいずれか。content と generatedAt は、ready の
    ときだけ入り、pending と failed では null。errorCode は、failed のときだけ入る。
    値は generation_failed か review_provider_error で、知らない値は generation_failed
    と同じに扱う。failed の行は、retry で pending に戻せる。

    content の形は contentVersion で決まる。daily-digest-v1 は items、overdueCount、
    dueTodayCount、doneYesterdayCount を、weekly-review-v1 は stats と summary を持つ。
    """

    id: UUID
    kind: DigestKind
    period_start: date
    timezone: str
    status: DigestStatus
    content: dict[str, object] | None = None
    content_version: str
    error_code: str | None = None
    generated_at: datetime | None = None
