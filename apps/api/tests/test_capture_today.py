from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from hibi.modules.captures.today import (
    TodayCandidate,
    calculate_today_priority,
    local_day_end,
    rank_today,
)

JST = "Asia/Tokyo"
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 15:00 JST
CREATED = datetime(2026, 11, 1, tzinfo=UTC)


def _id(n: int) -> UUID:
    return UUID(int=n)


def _candidate(
    n: int,
    *,
    urgency: str | None = "0.50",
    due: datetime | None = None,
    created: datetime = CREATED,
) -> TodayCandidate:
    return TodayCandidate(
        capture_id=_id(n),
        urgency_score=None if urgency is None else Decimal(urgency),
        due_at=due,
        created_at=created,
    )


@pytest.mark.parametrize(
    ("now", "timezone", "expected"),
    [
        (NOW, JST, datetime(2026, 11, 10, 15, 0, tzinfo=UTC)),
        (
            datetime(2026, 3, 8, 12, 0, tzinfo=UTC),
            "America/New_York",
            datetime(2026, 3, 9, 4, 0, tzinfo=UTC),
        ),  # 23 時間の日
        (
            datetime(2026, 11, 1, 12, 0, tzinfo=UTC),
            "America/New_York",
            datetime(2026, 11, 2, 5, 0, tzinfo=UTC),
        ),  # 25 時間の日
        (NOW, "Not/AZone", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
    ],
)
def test_local_day_end(now: datetime, timezone: str, expected: datetime) -> None:
    assert local_day_end(now, timezone=timezone) == expected


def test_priority_adds_the_deadline_bonus() -> None:
    overdue = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    later_today = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)
    assert calculate_today_priority(_candidate(1), now=NOW) == Decimal("0.50")
    assert calculate_today_priority(_candidate(1, due=overdue), now=NOW) == Decimal("1.10")
    assert calculate_today_priority(_candidate(1, due=later_today), now=NOW) == Decimal("0.90")
    assert calculate_today_priority(_candidate(1, urgency=None), now=NOW) == Decimal("0.50")


def test_rank_orders_overdue_then_today_then_no_deadline_and_drops_later_days() -> None:
    candidates = [
        _candidate(1),  # 期限なし 0.5
        _candidate(2, due=datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),  # 超過 1.1
        _candidate(3, due=datetime(2026, 11, 10, 11, 0, tzinfo=UTC)),  # 今日 0.9
        _candidate(4, due=datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),  # 明日 対象外
        _candidate(5, due=datetime(2026, 11, 10, 15, 0, tzinfo=UTC)),  # ちょうど翌日 0 時 対象外
        _candidate(6, due=datetime(2026, 11, 10, 14, 59, tzinfo=UTC)),  # 1 分前 対象
    ]
    assert rank_today(candidates, now=NOW, timezone=JST, limit=10) == [
        _id(2),
        _id(3),
        _id(6),
        _id(1),
    ]


def test_high_urgency_without_a_deadline_beats_low_urgency_due_today() -> None:
    high = _candidate(1, urgency="0.95")
    low = _candidate(2, urgency="0.10", due=datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
    assert rank_today([low, high], now=NOW, timezone=JST, limit=5) == [_id(1), _id(2)]


def test_ties_are_broken_by_due_created_then_id_regardless_of_input_order() -> None:
    older = datetime(2026, 10, 1, tzinfo=UTC)
    a = _candidate(3, created=older)
    b = _candidate(2, created=CREATED)
    c = _candidate(1, created=CREATED)
    expected = [_id(3), _id(1), _id(2)]
    assert rank_today([a, b, c], now=NOW, timezone=JST, limit=5) == expected
    assert rank_today([c, b, a], now=NOW, timezone=JST, limit=5) == expected


def test_rank_applies_the_limit() -> None:
    candidates = [_candidate(n) for n in range(1, 8)]
    assert len(rank_today(candidates, now=NOW, timezone=JST, limit=3)) == 3


def test_a_tie_between_no_deadline_and_a_deadline_does_not_raise_and_puts_the_deadline_first() -> (
    None
):
    no_deadline = _candidate(1, urgency="0.90")
    due_today = _candidate(2, urgency="0.50", due=datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
    assert rank_today([no_deadline, due_today], now=NOW, timezone=JST, limit=5) == [_id(2), _id(1)]
