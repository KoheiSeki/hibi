from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from hibi.core.timezone import local_day_start, to_local

_DEFAULT_URGENCY = Decimal("0.5")

_OVERDUE_BONUS = Decimal("0.6")
_DUE_TODAY_BONUS = Decimal("0.4")

_NO_DEADLINE = datetime.max.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class TodayCandidate:
    """Today の順位付けに使う、未完了のシナリオ 1 件。

    Attributes:
        capture_id: Capture の id。
        urgency_score: Jev の緊急度。0 以上 1 以下。未保存の行は None。
        due_at: 期限。UTC の aware な datetime。期限なしは None。
        created_at: Capture の作成時刻。同点のときの並びに使う。
    """

    capture_id: UUID
    urgency_score: Decimal | None
    due_at: datetime | None
    created_at: datetime


def local_day_end(now: datetime, *, timezone: str) -> datetime:
    """ユーザーの暦日の終わりを、UTC の aware な datetime で返す。

    終わりは、now がある暦日の翌日 0 時。暦日で数えるので、夏時間の日は
    23 時間や 25 時間になる。

    Args:
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。不正な名前は UTC として扱う。

    Returns:
        翌日 0 時に当たる UTC の時刻。この時刻ちょうどの期限は明日の扱い。
    """

    next_date = to_local(now, timezone=timezone).date() + timedelta(days=1)
    return local_day_start(next_date, timezone=timezone)


def calculate_today_priority(candidate: TodayCandidate, *, now: datetime) -> Decimal:
    """候補の優先度を、緊急度に期限の補正を足して返す。

    基準は urgency_score で、null は 0.5。期限なしは補正なし、期限が now より
    前なら +0.6、now 以降なら +0.4。今日の終わりを過ぎた期限の除外は
    ここでは行わず、`rank_today` が行う。

    Args:
        candidate: 優先度を求める候補。
        now: 現在時刻。aware な datetime。

    Returns:
        優先度。大きいほど先に出す。
    """

    base = _DEFAULT_URGENCY if candidate.urgency_score is None else candidate.urgency_score
    if candidate.due_at is None:
        return base

    bonus = _OVERDUE_BONUS if candidate.due_at < now else _DUE_TODAY_BONUS
    return base + bonus


def rank_today(
    candidates: Sequence[TodayCandidate], *, now: datetime, timezone: str, limit: int
) -> list[UUID]:
    """今日やることを、優先度の高い順に最大 limit 件の capture_id で返す。

    期限が今日の終わり以降の候補は対象外にする。今日の終わりは、ユーザーの
    暦日の翌日 0 時で、ちょうどその時刻の期限は明日の扱い。期限が過ぎた候補は
    日付に関係なく対象に残す。

    並びは次の順で決め、入力の順序には依存しない。

    1. 優先度の降順。`calculate_today_priority` の値。
    2. 期限の昇順。期限なしは最後。
    3. 作成日時の昇順。
    4. capture_id の昇順。

    Args:
        candidates: 未完了のシナリオを持つ候補。
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。不正な名前は UTC として扱う。
        limit: 返す最大件数。1 以上を呼び出し側が保証する。

    Returns:
        優先度の高い順の capture_id。対象が無ければ空のリスト。
    """

    day_end = local_day_end(now, timezone=timezone)
    eligible = [
        candidate
        for candidate in candidates
        if candidate.due_at is None or candidate.due_at < day_end
    ]
    ranked_candidates = sorted(eligible, key=lambda item: _sort_key(item, now=now))
    return [candidate.capture_id for candidate in ranked_candidates[:limit]]


def _sort_key(
    candidate: TodayCandidate, *, now: datetime
) -> tuple[Decimal, datetime, datetime, UUID]:
    """`rank_today` が並べ替えに使うキーを返す。小さいキーほど先に出る。

    優先度は大きいほど先なので、符号を反転して先頭に置く。期限なしは None の
    ままだと datetime と比べられず例外になるため、どの期限よりも後の
    `_NO_DEADLINE` に置き換えて最後にする。

    Args:
        candidate: キーを求める候補。
        now: 現在時刻。aware な datetime。

    Returns:
        優先度の符号反転、期限、作成日時、capture_id の順のタプル。
    """

    return (
        -calculate_today_priority(candidate, now=now),
        candidate.due_at or _NO_DEADLINE,
        candidate.created_at,
        candidate.capture_id,
    )
