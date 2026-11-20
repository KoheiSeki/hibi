from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from hibi.modules.captures.today import TodayCandidate
from hibi.modules.digests.content import (
    EMPTY_WEEK_SUMMARY,
    SUMMARY_FALLBACK_TEXT,
    WEEKLY_SUMMARY_MAX_LENGTH,
    DeadlineCounts,
    DigestItem,
    WeeklyStats,
    build_daily_content,
    build_weekly_content,
    count_deadlines,
    normalize_summary,
)

NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 15:00 JST
JST = "Asia/Tokyo"


def _candidate(n: int, due: datetime | None) -> TodayCandidate:
    return TodayCandidate(
        capture_id=UUID(int=n), urgency_score=Decimal("0.50"), due_at=due, created_at=NOW
    )


def test_count_deadlines_separates_overdue_from_due_today() -> None:
    candidates = [
        _candidate(1, datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),  # 超過
        _candidate(2, datetime(2026, 11, 10, 11, 0, tzinfo=UTC)),  # 今日
        _candidate(3, datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),  # 明日は数えない
        _candidate(4, None),  # 期限なしは数えない
    ]
    assert count_deadlines(candidates, now=NOW, timezone=JST) == DeadlineCounts(
        overdue_count=1, due_today_count=1
    )


def test_build_daily_content_uses_camel_case_keys_and_iso_times() -> None:
    items = [
        DigestItem(UUID(int=1), "起こして", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
        DigestItem(UUID(int=2), "牛乳", None),
    ]
    content = build_daily_content(
        items=items, deadline_counts=DeadlineCounts(1, 2), done_yesterday_count=3
    )
    assert content == {
        "items": [
            {"captureId": str(UUID(int=1)), "title": "起こして", "dueAt": "2026-11-11T00:00:00Z"},
            {"captureId": str(UUID(int=2)), "title": "牛乳", "dueAt": None},
        ],
        "overdueCount": 1,
        "dueTodayCount": 2,
        "doneYesterdayCount": 3,
    }


def test_build_daily_content_for_no_items_is_still_valid() -> None:
    content = build_daily_content(
        items=[], deadline_counts=DeadlineCounts(0, 0), done_yesterday_count=0
    )
    assert content["items"] == []


def test_build_weekly_content_keeps_camel_case_keys() -> None:
    content = build_weekly_content(
        stats=WeeklyStats(captured_count=5, done_count=3, open_count=2, overdue_count=1),
        summary="先週は 3 件を終わらせました。",
    )

    assert content == {
        "stats": {"capturedCount": 5, "doneCount": 3, "openCount": 2, "overdueCount": 1},
        "summary": "先週は 3 件を終わらせました。",
    }


@pytest.mark.parametrize(
    "summary", ["先週は 3 件を終わらせました。", "あ", "あ" * WEEKLY_SUMMARY_MAX_LENGTH]
)
def test_normalize_summary_keeps_a_valid_summary(summary: str) -> None:
    assert normalize_summary(summary) == summary


@pytest.mark.parametrize("summary", ["", "   ", "\n", "あ" * (WEEKLY_SUMMARY_MAX_LENGTH + 1)])
def test_normalize_summary_replaces_an_invalid_summary_with_the_fallback(summary: str) -> None:
    assert normalize_summary(summary) == SUMMARY_FALLBACK_TEXT


def test_the_fixed_summaries_fit_in_the_maximum_length() -> None:
    assert WEEKLY_SUMMARY_MAX_LENGTH == 500
    assert 0 < len(EMPTY_WEEK_SUMMARY) <= WEEKLY_SUMMARY_MAX_LENGTH
    assert 0 < len(SUMMARY_FALLBACK_TEXT) <= WEEKLY_SUMMARY_MAX_LENGTH
    assert EMPTY_WEEK_SUMMARY != SUMMARY_FALLBACK_TEXT
