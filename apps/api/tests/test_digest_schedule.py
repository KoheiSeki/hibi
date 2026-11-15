from datetime import UTC, date, datetime

import pytest

from hibi.modules.digests.schedule import (
    daily_period_start,
    local_day_start,
    weekly_period_start,
)

JST = "Asia/Tokyo"
NY = "America/New_York"


@pytest.mark.parametrize(
    ("now", "timezone", "expected"),
    [
        # JST 06:59 と 07:00
        (datetime(2026, 11, 10, 21, 59, tzinfo=UTC), JST, None),
        (datetime(2026, 11, 10, 22, 0, tzinfo=UTC), JST, date(2026, 11, 11)),
        # 夏時間の開始日(23 時間の日)。EDT の 07:00 は 11:00 UTC
        (datetime(2026, 3, 8, 10, 59, tzinfo=UTC), NY, None),
        (datetime(2026, 3, 8, 11, 0, tzinfo=UTC), NY, date(2026, 3, 8)),
        # 夏時間の終了日(25 時間の日)。EST の 07:00 は 12:00 UTC
        (datetime(2026, 11, 1, 11, 59, tzinfo=UTC), NY, None),
        (datetime(2026, 11, 1, 12, 0, tzinfo=UTC), NY, date(2026, 11, 1)),
        # 不正な名前は UTC として扱う
        (datetime(2026, 11, 10, 7, 0, tzinfo=UTC), "Not/AZone", date(2026, 11, 10)),
    ],
)
def test_daily_period_start(now: datetime, timezone: str, expected: date | None) -> None:
    assert daily_period_start(now, timezone=timezone) == expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # 2026-11-09 は月曜。JST 06:59 と 07:00
        (datetime(2026, 11, 8, 21, 59, tzinfo=UTC), None),
        (datetime(2026, 11, 8, 22, 0, tzinfo=UTC), date(2026, 11, 2)),
        # 月曜の夜でも、その日のうちは作る
        (datetime(2026, 11, 9, 14, 0, tzinfo=UTC), date(2026, 11, 2)),
        # 火曜以降は作らない
        (datetime(2026, 11, 9, 22, 0, tzinfo=UTC), None),
        (datetime(2026, 11, 13, 0, 0, tzinfo=UTC), None),
    ],
)
def test_weekly_period_start(now: datetime, expected: date | None) -> None:
    assert weekly_period_start(now, timezone=JST) == expected


def test_weekly_period_start_uses_the_local_weekday() -> None:
    # UTC では日曜 23:00 だが、JST では月曜 08:00
    assert weekly_period_start(datetime(2026, 11, 8, 23, 0, tzinfo=UTC), timezone=JST) == date(
        2026, 11, 2
    )


@pytest.mark.parametrize(
    ("day", "timezone", "expected"),
    [
        (date(2026, 11, 10), JST, datetime(2026, 11, 9, 15, 0, tzinfo=UTC)),
        (date(2026, 3, 8), NY, datetime(2026, 3, 8, 5, 0, tzinfo=UTC)),
        (date(2026, 11, 1), NY, datetime(2026, 11, 1, 4, 0, tzinfo=UTC)),
    ],
)
def test_local_day_start(day: date, timezone: str, expected: datetime) -> None:
    assert local_day_start(day, timezone=timezone) == expected
