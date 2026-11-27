from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from hibi.ai.review_summary import WeeklyStats
from hibi.modules.captures.today import TodayCandidate, local_day_end

DAILY_ITEM_LIMIT = 5
DAILY_CONTENT_VERSION = "daily-digest-v1"
WEEKLY_CONTENT_VERSION = "weekly-review-v1"

WEEKLY_SUMMARY_MAX_LENGTH = 500

# Capture が 1 件も無い週の要約。LLM を呼ばずに、この文で ready にする
EMPTY_WEEK_SUMMARY = "先週は記録がありませんでした。今週も気軽に書き留めてみましょう。"
# 要約が空、または長すぎたときの定型文。LLM の出力が使えなかったことは、利用者に見せない
SUMMARY_FALLBACK_TEXT = "先週の記録をまとめました。下の数字で振り返ってみましょう。"


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


def build_weekly_content(*, stats: WeeklyStats, summary: str) -> dict[str, object]:
    """週次レビューの内容を、DB の `jsonb` に保存できる辞書にする。

    キーは camelCase で、API のレスポンスの `content` に、そのまま出る。集計は
    `stats` の下にまとめ、要約は `summary` に入れる。

    要約は検査しない。呼び出し側が、LLM の要約なら `normalize_summary` を通した値を、
    Capture が無い週なら `EMPTY_WEEK_SUMMARY` を渡す。ここで検査すると、上限の
    判定が 2 か所に分かれるため。

    Args:
        stats: 先週の件数の集計。
        summary: 画面に出す要約。500 文字以内で、空でない。

    Returns:
        `stats`(`capturedCount`、`doneCount`、`openCount`、`overdueCount`)と
        `summary` を持つ辞書。
    """

    return {
        "stats": {
            "capturedCount": stats.captured_count,
            "doneCount": stats.done_count,
            "openCount": stats.open_count,
            "overdueCount": stats.overdue_count,
        },
        "summary": summary,
    }


def normalize_summary(text: str) -> str:
    """要約が画面に出せる形なら、そのまま返す。出せなければ定型文に置き換える。

    空、空白だけ、または `WEEKLY_SUMMARY_MAX_LENGTH` 文字を超える要約は、
    `SUMMARY_FALLBACK_TEXT` にする。LLM が不正な出力を返したときも、再試行せず、
    この定型文で週次レビューを `ready` にする(spec の決定)。要約の検査は、adapter
    ではなく、ここ 1 か所で行う。上限を変えるときに、片方を直し忘れないため。

    正しい要約は、前後の空白も含めて、手を加えずに返す。切り詰めると、文の途中で
    切れた要約が画面に出てしまうので、長すぎる要約は、切らずに定型文にする。

    Args:
        text: 要約。LLM の adapter が返した値で、取り出せなかったときは空の文字列。

    Returns:
        画面に出す要約。500 文字以内で、空ではない。
    """

    if text.strip() == "" or len(text) > WEEKLY_SUMMARY_MAX_LENGTH:
        return SUMMARY_FALLBACK_TEXT
    return text


def _to_iso(value: datetime | None) -> str | None:
    """UTC の aware な datetime を、`Z` 表記の ISO 8601 にする。None はそのまま返す。"""

    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
