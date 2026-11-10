from datetime import UTC, datetime

import pytest

from hibi.modules.captures.due import extract_remind_text, parse_due_at

# 2026-11-10 15:00 JST
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
JST = "Asia/Tokyo"


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("明日の 9 時に起こして", "明日の 9 時"),
        ("午後3時に会議", "午後3時"),
        ("明日までに提出", "明日"),
        ("今日の 9 時 30 分に電話", "今日の 9 時 30 分"),
        ("牛乳を買う", None),
        ("3時間かかる", None),
    ],
)
def test_extract_remind_text(raw_text: str, expected: str | None) -> None:
    assert extract_remind_text(raw_text) == expected


@pytest.mark.parametrize(
    ("remind_text", "expected"),
    [
        ("明日の 9 時", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
        ("午後3時", datetime(2026, 11, 10, 6, 0, tzinfo=UTC)),
        ("今日の 9 時 30 分", datetime(2026, 11, 10, 0, 30, tzinfo=UTC)),
        ("明日の 9 時半", datetime(2026, 11, 11, 0, 30, tzinfo=UTC)),
        ("明後日の 9 時", datetime(2026, 11, 12, 0, 0, tzinfo=UTC)),
        ("明日", datetime(2026, 11, 11, 14, 59, tzinfo=UTC)),
    ],
)
def test_parse_due_at_in_the_user_timezone(remind_text: str, expected: datetime) -> None:
    assert parse_due_at(remind_text, now=NOW, timezone=JST) == expected


def test_parse_due_at_uses_the_local_date_of_now() -> None:
    # UTC では 11/10 20:00 だが JST では 11/11 05:00
    now = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
    assert parse_due_at("今日の 9 時", now=now, timezone=JST) == datetime(
        2026, 11, 11, 0, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("remind_text", ["25 時", "9 時 60 分", "ランチ"])
def test_parse_due_at_returns_none_for_invalid_or_missing_expressions(remind_text: str) -> None:
    assert parse_due_at(remind_text, now=NOW, timezone=JST) is None


def test_parse_due_at_treats_an_unknown_timezone_as_utc() -> None:
    assert parse_due_at("明日の 9 時", now=NOW, timezone="Not/AZone") == datetime(
        2026, 11, 11, 9, 0, tzinfo=UTC
    )
