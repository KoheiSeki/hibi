from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from hibi.modules.digests.service import DigestService

from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.today import TodayCandidate
from hibi.modules.captures.types import CAPTURE_STATUS_COMPLETED, Capture, CaptureScenario
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.types import (
    DIGEST_KIND_DAILY,
    DIGEST_STATUS_FAILED,
    DIGEST_STATUS_PENDING,
    DIGEST_STATUS_READY,
    ActiveUser,
    DigestReport,
)

_TOKYO_USER = ActiveUser(user_id=UUID(int=10), timezone="Asia/Tokyo")
_NEW_YORK_USER = ActiveUser(user_id=UUID(int=11), timezone="America/New_York")

_CREATED = datetime(2026, 11, 1, tzinfo=UTC)
# 2026-11-10 15:00 JST。Today のテストと同じ時刻と期限を使う
_NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
_OVERDUE = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)  # 09:00 JST
_LATER_TODAY = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)  # 20:00 JST

_NO_DEADLINE_ID = UUID(int=1)
_OVERDUE_ID = UUID(int=2)
_TODAY_ID = UUID(int=3)

_ClaimKey = tuple[UUID, str, date]


class FakeDigestRepository:
    """`DigestRepository` の代わりに、呼び出しを記録する fake。"""

    def __init__(
        self,
        *,
        users: Sequence[ActiveUser] = (),
        report: DigestReport | None = None,
        existing: frozenset[_ClaimKey] = frozenset(),
        done_count: int = 0,
    ) -> None:
        self.users = list(users)
        self.report = report
        self.existing = existing
        self.done_count = done_count
        self.active_user_calls: list[dict[str, object]] = []
        self.claims: list[dict[str, object]] = []
        self.completed: list[tuple[UUID, dict[str, object], str | None]] = []
        self.failed: list[tuple[UUID, str]] = []
        self.done_calls: list[tuple[UUID, datetime, datetime]] = []

    async def list_active_users(self, *, active_since: datetime, limit: int) -> list[ActiveUser]:
        self.active_user_calls.append({"active_since": active_since, "limit": limit})
        return self.users

    async def claim_report(
        self,
        *,
        report_id: UUID,
        user_id: UUID,
        kind: str,
        period_start: date,
        timezone: str,
        content_version: str,
        outbox_id: UUID,
    ) -> bool:
        self.claims.append(
            {
                "report_id": report_id,
                "user_id": user_id,
                "kind": kind,
                "period_start": period_start,
                "timezone": timezone,
                "content_version": content_version,
                "outbox_id": outbox_id,
            }
        )
        return (user_id, kind, period_start) not in self.existing

    async def get_report(self, report_id: UUID) -> DigestReport | None:
        if self.report is not None and self.report.id == report_id:
            return self.report
        return None

    async def complete_report(
        self, report_id: UUID, *, content: dict[str, object], summary_model: str | None
    ) -> bool:
        self.completed.append((report_id, content, summary_model))
        return True

    async def fail_report(self, report_id: UUID, *, error_code: str) -> bool:
        self.failed.append((report_id, error_code))
        return True

    async def count_done_between(self, user_id: UUID, *, start: datetime, end: datetime) -> int:
        self.done_calls.append((user_id, start, end))
        return self.done_count


class FakeCaptureRepository:
    """`CaptureRepository` の代わりに、Today の候補を返す fake。"""

    def __init__(self, candidates: Sequence[TodayCandidate] = ()) -> None:
        self.candidates = list(candidates)
        self.candidate_reads: list[UUID] = []
        self.by_ids_calls: list[list[UUID]] = []

    async def list_open_scenario_candidates(self, user_id: UUID) -> list[TodayCandidate]:
        self.candidate_reads.append(user_id)
        return self.candidates

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        self.by_ids_calls.append(list(capture_ids))
        due_by_id = {candidate.capture_id: candidate.due_at for candidate in self.candidates}
        # 順位の逆順で返し、service が順位どおりに並べ直すことを確かめる
        return [_capture(capture_id, due_by_id[capture_id]) for capture_id in reversed(capture_ids)]


def _title(capture_id: UUID) -> str:
    return f"title-{capture_id.int}"


def _capture(capture_id: UUID, due_at: datetime | None) -> Capture:
    return Capture(
        id=capture_id,
        user_id=_TOKYO_USER.user_id,
        raw_text="本文は、ダイジェストに出さない",
        status=CAPTURE_STATUS_COMPLETED,
        idempotency_key=str(capture_id),
        request_hash="a" * 64,
        processing_generation=1,
        category="reminder",
        route="reminder",
        urgency="normal",
        confidence=None,
        policy_version=None,
        question_version=None,
        processed_at=_CREATED,
        clarification_text=None,
        created_at=_CREATED,
        updated_at=_CREATED,
        scenario=CaptureScenario(
            route="reminder",
            status="accepted",
            title=_title(capture_id),
            amount=None,
            remind_text=None,
            policy_version="v1",
            due_at=due_at,
        ),
    )


def _candidate(capture_id: UUID, *, due_at: datetime | None = None) -> TodayCandidate:
    return TodayCandidate(
        capture_id=capture_id,
        urgency_score=Decimal("0.50"),
        due_at=due_at,
        created_at=_CREATED,
    )


def _report(
    *,
    kind: str = DIGEST_KIND_DAILY,
    status: str = DIGEST_STATUS_PENDING,
    period_start: date = date(2026, 11, 10),
    timezone: str = "Asia/Tokyo",
) -> DigestReport:
    return DigestReport(
        id=UUID(int=100),
        user_id=_TOKYO_USER.user_id,
        kind=kind,
        period_start=period_start,
        timezone=timezone,
        status=status,
        content=None,
        content_version="daily-digest-v1",
        summary_model=None,
        error_code=None,
        generated_at=None,
        created_at=_CREATED,
        updated_at=_CREATED,
    )


def _service(
    digests: FakeDigestRepository,
    captures: FakeCaptureRepository | None = None,
    *,
    now: datetime = _NOW,
) -> DigestService:
    return DigestService(
        digests=cast(DigestRepository, digests),
        captures=cast(CaptureRepository, captures or FakeCaptureRepository()),
        clock=lambda: now,
    )


def _claimed(digests: FakeDigestRepository) -> set[tuple[UUID, str, date, str, str]]:
    return {
        (
            cast(UUID, claim["user_id"]),
            cast(str, claim["kind"]),
            cast(date, claim["period_start"]),
            cast(str, claim["timezone"]),
            cast(str, claim["content_version"]),
        )
        for claim in digests.claims
    }


@pytest.mark.asyncio
async def test_schedule_claims_daily_only_after_seven_in_the_user_timezone() -> None:
    # 22:00 UTC は、東京では翌日の 07:00、ニューヨークでは 17:00(どちらも 7 時以降)
    digests = FakeDigestRepository(users=[_TOKYO_USER, _NEW_YORK_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 2
    assert _claimed(digests) == {
        (_TOKYO_USER.user_id, "daily", date(2026, 11, 11), "Asia/Tokyo", "daily-digest-v1"),
        (
            _NEW_YORK_USER.user_id,
            "daily",
            date(2026, 11, 10),
            "America/New_York",
            "daily-digest-v1",
        ),
    }


@pytest.mark.asyncio
async def test_schedule_skips_a_user_before_seven_in_the_user_timezone() -> None:
    # 21:59 UTC は、東京では 06:59。ニューヨークは 16:59 で対象のまま
    digests = FakeDigestRepository(users=[_TOKYO_USER, _NEW_YORK_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 10, 21, 59, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 1
    assert [claim["user_id"] for claim in digests.claims] == [_NEW_YORK_USER.user_id]


@pytest.mark.asyncio
async def test_schedule_does_not_claim_weekly_on_a_tuesday() -> None:
    # 2026-11-10 は火曜。東京は 09:00
    digests = FakeDigestRepository(users=[_TOKYO_USER])

    await _service(digests, now=datetime(2026, 11, 10, 0, 0, tzinfo=UTC)).schedule_due_reports()

    assert [claim["kind"] for claim in digests.claims] == [DIGEST_KIND_DAILY]


@pytest.mark.asyncio
async def test_schedule_claims_weekly_on_monday_with_last_monday_as_the_period() -> None:
    # 2026-11-09 は月曜。東京は 09:00。先週の月曜は 11-02
    digests = FakeDigestRepository(users=[_TOKYO_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 2
    assert _claimed(digests) == {
        (_TOKYO_USER.user_id, "daily", date(2026, 11, 9), "Asia/Tokyo", "daily-digest-v1"),
        (_TOKYO_USER.user_id, "weekly", date(2026, 11, 2), "Asia/Tokyo", "weekly-review-v1"),
    }


@pytest.mark.asyncio
async def test_schedule_claims_nothing_on_monday_before_seven() -> None:
    # 2026-11-08 21:59 UTC は、東京では月曜の 06:59
    digests = FakeDigestRepository(users=[_TOKYO_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 8, 21, 59, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 0
    assert digests.claims == []


@pytest.mark.asyncio
async def test_schedule_counts_only_the_reports_that_were_newly_claimed() -> None:
    # 東京の daily は既にある。claim は試みるが、数えない
    digests = FakeDigestRepository(
        users=[_TOKYO_USER, _NEW_YORK_USER],
        existing=frozenset({(_TOKYO_USER.user_id, "daily", date(2026, 11, 11))}),
    )

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 1
    assert len(digests.claims) == 2


@pytest.mark.asyncio
async def test_schedule_reads_only_users_active_in_the_last_14_days() -> None:
    digests = FakeDigestRepository()

    await _service(digests).schedule_due_reports()

    [call] = digests.active_user_calls
    assert call["active_since"] == _NOW - timedelta(days=14)


@pytest.mark.asyncio
async def test_schedule_issues_distinct_ids_for_each_report_and_outbox_event() -> None:
    digests = FakeDigestRepository(users=[_TOKYO_USER])

    await _service(digests, now=datetime(2026, 11, 9, 0, 0, tzinfo=UTC)).schedule_due_reports()

    ids = [claim[key] for claim in digests.claims for key in ("report_id", "outbox_id")]
    assert len(ids) == 4
    assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_generate_daily_report_completes_with_ranked_items() -> None:
    digests = FakeDigestRepository(report=_report(), done_count=2)
    captures = FakeCaptureRepository(
        [
            _candidate(_NO_DEADLINE_ID),
            _candidate(_OVERDUE_ID, due_at=_OVERDUE),
            _candidate(_TODAY_ID, due_at=_LATER_TODAY),
        ]
    )

    await _service(digests, captures).generate_report(UUID(int=100))

    assert digests.completed == [
        (
            UUID(int=100),
            {
                "items": [
                    {
                        "captureId": str(_OVERDUE_ID),
                        "title": _title(_OVERDUE_ID),
                        "dueAt": "2026-11-10T00:00:00Z",
                    },
                    {
                        "captureId": str(_TODAY_ID),
                        "title": _title(_TODAY_ID),
                        "dueAt": "2026-11-10T11:00:00Z",
                    },
                    {
                        "captureId": str(_NO_DEADLINE_ID),
                        "title": _title(_NO_DEADLINE_ID),
                        "dueAt": None,
                    },
                ],
                "overdueCount": 1,
                "dueTodayCount": 1,
                "doneYesterdayCount": 2,
            },
            None,
        )
    ]
    assert digests.failed == []


@pytest.mark.asyncio
async def test_generate_daily_report_never_puts_the_raw_text_in_the_content() -> None:
    digests = FakeDigestRepository(report=_report())
    captures = FakeCaptureRepository([_candidate(_NO_DEADLINE_ID)])

    await _service(digests, captures).generate_report(UUID(int=100))

    [(_, content, _)] = digests.completed
    assert "本文は、ダイジェストに出さない" not in str(content)


@pytest.mark.asyncio
async def test_generate_daily_report_limits_the_items_to_five() -> None:
    digests = FakeDigestRepository(report=_report())
    captures = FakeCaptureRepository([_candidate(UUID(int=n)) for n in range(1, 9)])

    await _service(digests, captures).generate_report(UUID(int=100))

    [(_, content, _)] = digests.completed
    assert len(cast(list[object], content["items"])) == 5


@pytest.mark.asyncio
async def test_generate_daily_report_counts_yesterday_in_the_report_timezone() -> None:
    # 期間の日付が 11-10 なら、昨日は 11-09。東京の 11-09 0 時から 11-10 0 時まで
    digests = FakeDigestRepository(report=_report(period_start=date(2026, 11, 10)))

    await _service(digests).generate_report(UUID(int=100))

    assert digests.done_calls == [
        (
            _TOKYO_USER.user_id,
            datetime(2026, 11, 8, 15, 0, tzinfo=UTC),
            datetime(2026, 11, 9, 15, 0, tzinfo=UTC),
        )
    ]


@pytest.mark.asyncio
async def test_generate_daily_report_without_candidates_completes_with_an_empty_digest() -> None:
    digests = FakeDigestRepository(report=_report())
    captures = FakeCaptureRepository()

    await _service(digests, captures).generate_report(UUID(int=100))

    [(_, content, _)] = digests.completed
    assert content["items"] == []
    assert content["overdueCount"] == 0
    assert content["dueTodayCount"] == 0
    assert captures.by_ids_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DIGEST_STATUS_READY, DIGEST_STATUS_FAILED])
async def test_generate_report_does_nothing_unless_pending(status: str) -> None:
    digests = FakeDigestRepository(report=_report(status=status))
    captures = FakeCaptureRepository([_candidate(_NO_DEADLINE_ID)])

    await _service(digests, captures).generate_report(UUID(int=100))

    assert digests.completed == []
    assert digests.failed == []
    assert captures.candidate_reads == []


@pytest.mark.asyncio
async def test_generate_report_does_nothing_for_a_missing_report() -> None:
    digests = FakeDigestRepository()

    await _service(digests).generate_report(UUID(int=100))

    assert digests.completed == []
    assert digests.failed == []
