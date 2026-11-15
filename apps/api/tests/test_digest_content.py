from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from hibi.modules.captures.today import TodayCandidate
from hibi.modules.digests.content import (
    DeadlineCounts,
    DigestItem,
    build_daily_content,
    count_deadlines,
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
