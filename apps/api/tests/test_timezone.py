from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from hibi.core.timezone import local_day_start, to_local, zone_for


def test_zone_for_returns_the_named_zone() -> None:
    assert zone_for("Asia/Tokyo") == ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize("name", ["", "Asia", "Asia/", "../etc/passwd", "Not/AZone"])
def test_zone_for_falls_back_to_utc_for_unknown_or_invalid_names(name: str) -> None:
    assert zone_for(name) == ZoneInfo("UTC")


def test_to_local_keeps_the_instant_and_changes_the_representation() -> None:
    now = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)

    local = to_local(now, timezone="Asia/Tokyo")

    assert local == now
    assert (local.date(), local.hour) == (date(2026, 11, 11), 5)


def test_to_local_treats_an_unknown_name_as_utc() -> None:
    now = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)

    assert to_local(now, timezone="Not/AZone").hour == 20


@pytest.mark.parametrize(
    ("day", "timezone", "expected"),
    [
        (date(2026, 11, 10), "Asia/Tokyo", datetime(2026, 11, 9, 15, 0, tzinfo=UTC)),
        # 夏時間の開始日と終了日。0 時の時点の UTC との差で、切り替えの前後が分かる
        (date(2026, 3, 8), "America/New_York", datetime(2026, 3, 8, 5, 0, tzinfo=UTC)),
        (date(2026, 11, 1), "America/New_York", datetime(2026, 11, 1, 4, 0, tzinfo=UTC)),
        (date(2026, 11, 10), "Not/AZone", datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),
    ],
)
def test_local_day_start(day: date, timezone: str, expected: datetime) -> None:
    assert local_day_start(day, timezone=timezone) == expected
