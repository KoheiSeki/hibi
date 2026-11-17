from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from hibi.modules.captures.today import TodayCandidate, local_day_end

DAILY_ITEM_LIMIT = 5
DAILY_CONTENT_VERSION = "daily-digest-v1"
WEEKLY_CONTENT_VERSION = "weekly-review-v1"


@dataclass(frozen=True, slots=True)
class DigestItem:
    """日次ダイジェストに載せる、今日やることの1行。

    Attributes:
        capture_id: Capture の id。画面から詳細へ移るのに使う。
        title: シナリオの題。
        due_at: 期限。UTC の aware な datetime。期限なしは None。
    """

    capture_id: UUID
    title: str
    due_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeadlineCounts:
    """未完了のシナリオの、期限による件数。

    Attributes:
        overdue_count: 期限が現在時刻より前の件数。
        due_today_count: 期限が現在時刻以降で、今日の終わりより前の件数。
    """

    overdue_count: int
    due_today_count: int


def count_deadlines(
    candidates: Sequence[TodayCandidate], *, now: datetime, timezone: str
) -> DeadlineCounts:
    """未完了の候補から、期限が過ぎた件数と、今日が期限の件数を数える。

    今日の終わりは、ユーザーの暦日の翌日 0 時。期限なしと、明日以降の期限は
    どちらにも数えない。

    Args:
        candidates: 未完了のシナリオを持つ候補。
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。不正な名前は UTC として扱う。

    Returns:
        期限が過ぎた件数と、今日が期限の件数。
    """

    overdue_count: int = 0
    due_today_count: int = 0

    day_end = local_day_end(now, timezone=timezone)
    for candidate in candidates:
        if candidate.due_at is None:
            continue
        if candidate.due_at < now:
            overdue_count += 1
        elif candidate.due_at < day_end:
            due_today_count += 1

    return DeadlineCounts(overdue_count=overdue_count, due_today_count=due_today_count)


def build_daily_content(
    *, items: list[DigestItem], deadline_counts: DeadlineCounts, done_yesterday_count: int
) -> dict[str, object]:
    """日次ダイジェストの内容を、DB の `jsonb` に保存できる辞書にする。

    キーは camelCase で、時刻は UTC の ISO 8601(`Z` 表記)。API のレスポンスの
    `content` に、そのまま出る。`items` が空でも正常で、空の配列になる。

    Args:
        items: 今日やることの上位の行。優先度の高い順。
        deadline_counts: 期限が過ぎた件数と、今日が期限の件数。
        done_yesterday_count: 昨日、完了にした件数。

    Returns:
        `items`、`overdueCount`、`dueTodayCount`、`doneYesterdayCount` を持つ辞書。
    """

    return {
        "items": [
            {"captureId": str(item.capture_id), "title": item.title, "dueAt": _to_iso(item.due_at)}
            for item in items
        ],
        "overdueCount": deadline_counts.overdue_count,
        "dueTodayCount": deadline_counts.due_today_count,
        "doneYesterdayCount": done_yesterday_count,
    }


def _to_iso(value: datetime | None) -> str | None:
    """UTC の aware な datetime を、`Z` 表記の ISO 8601 にする。None はそのまま返す。"""

    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
