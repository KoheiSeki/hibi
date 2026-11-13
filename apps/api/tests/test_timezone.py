from zoneinfo import ZoneInfo

import pytest

from hibi.core.timezone import zone_for


def test_zone_for_returns_the_named_zone() -> None:
    assert zone_for("Asia/Tokyo") == ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize("name", ["", "Asia", "Asia/", "../etc/passwd", "Not/AZone"])
def test_zone_for_falls_back_to_utc_for_unknown_or_invalid_names(name: str) -> None:
    assert zone_for(name) == ZoneInfo("UTC")
