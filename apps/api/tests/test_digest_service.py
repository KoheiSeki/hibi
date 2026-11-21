from datetime import UTC, date, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from digest_helpers import (
    LATER_TODAY,
    NEW_YORK_USER,
    NO_DEADLINE_ID,
    NOW,
    OVERDUE,
    OVERDUE_ID,
    TODAY_ID,
    TOKYO_USER,
    FakeCaptureRepository,
    FakeDigestRepository,
    FakeSummarizer,
    make_candidate,
    make_report,
    title_of,
)

from hibi.ai.review_summary import ReviewSummarizer
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.errors import DigestReportNotFoundError, DigestReportNotRetryableError
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.service import DigestService
from hibi.modules.digests.types import (
    DIGEST_KIND_DAILY,
    DIGEST_STATUS_FAILED,
    DIGEST_STATUS_PENDING,
    DIGEST_STATUS_READY,
    ListDigestReportsQuery,
)


def _service(
    digests: FakeDigestRepository,
    captures: FakeCaptureRepository | None = None,
    *,
    now: datetime = NOW,
) -> DigestService:
    return DigestService(
        digests=cast(DigestRepository, digests),
        captures=cast(CaptureRepository, captures or FakeCaptureRepository()),
        summarizer=cast(ReviewSummarizer, FakeSummarizer()),
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
    digests = FakeDigestRepository(users=[TOKYO_USER, NEW_YORK_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 2
    assert _claimed(digests) == {
        (TOKYO_USER.user_id, "daily", date(2026, 11, 11), "Asia/Tokyo", "daily-digest-v1"),
        (
            NEW_YORK_USER.user_id,
            "daily",
            date(2026, 11, 10),
            "America/New_York",
            "daily-digest-v1",
        ),
    }


@pytest.mark.asyncio
async def test_schedule_skips_a_user_before_seven_in_the_user_timezone() -> None:
    # 21:59 UTC は、東京では 06:59。ニューヨークは 16:59 で対象のまま
    digests = FakeDigestRepository(users=[TOKYO_USER, NEW_YORK_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 10, 21, 59, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 1
    assert [claim["user_id"] for claim in digests.claims] == [NEW_YORK_USER.user_id]


@pytest.mark.asyncio
async def test_schedule_does_not_claim_weekly_on_a_tuesday() -> None:
    # 2026-11-10 は火曜。東京は 09:00
    digests = FakeDigestRepository(users=[TOKYO_USER])

    await _service(digests, now=datetime(2026, 11, 10, 0, 0, tzinfo=UTC)).schedule_due_reports()

    assert [claim["kind"] for claim in digests.claims] == [DIGEST_KIND_DAILY]


@pytest.mark.asyncio
async def test_schedule_claims_weekly_on_monday_with_last_monday_as_the_period() -> None:
    # 2026-11-09 は月曜。東京は 09:00。先週の月曜は 11-02
    digests = FakeDigestRepository(users=[TOKYO_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 2
    assert _claimed(digests) == {
        (TOKYO_USER.user_id, "daily", date(2026, 11, 9), "Asia/Tokyo", "daily-digest-v1"),
        (TOKYO_USER.user_id, "weekly", date(2026, 11, 2), "Asia/Tokyo", "weekly-review-v1"),
    }


@pytest.mark.asyncio
async def test_schedule_claims_nothing_on_monday_before_seven() -> None:
    # 2026-11-08 21:59 UTC は、東京では月曜の 06:59
    digests = FakeDigestRepository(users=[TOKYO_USER])

    claimed_count = await _service(
        digests, now=datetime(2026, 11, 8, 21, 59, tzinfo=UTC)
    ).schedule_due_reports()

    assert claimed_count == 0
    assert digests.claims == []


@pytest.mark.asyncio
async def test_schedule_counts_only_the_reports_that_were_newly_claimed() -> None:
    # 東京の daily は既にある。claim は試みるが、数えない
    digests = FakeDigestRepository(
        users=[TOKYO_USER, NEW_YORK_USER],
        existing=frozenset({(TOKYO_USER.user_id, "daily", date(2026, 11, 11))}),
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
    assert call["active_since"] == NOW - timedelta(days=14)


@pytest.mark.asyncio
async def test_schedule_issues_distinct_ids_for_each_report_and_outbox_event() -> None:
    digests = FakeDigestRepository(users=[TOKYO_USER])

    await _service(digests, now=datetime(2026, 11, 9, 0, 0, tzinfo=UTC)).schedule_due_reports()

    ids = [claim[key] for claim in digests.claims for key in ("report_id", "outbox_id")]
    assert len(ids) == 4
    assert len(set(ids)) == 4


@pytest.mark.asyncio
async def test_generate_daily_report_completes_with_ranked_items() -> None:
    digests = FakeDigestRepository(report=make_report(), done_count=2)
    captures = FakeCaptureRepository(
        [
            make_candidate(NO_DEADLINE_ID),
            make_candidate(OVERDUE_ID, due_at=OVERDUE),
            make_candidate(TODAY_ID, due_at=LATER_TODAY),
        ]
    )

    await _service(digests, captures).generate_report(UUID(int=100))

    assert digests.completed == [
        (
            UUID(int=100),
            {
                "items": [
                    {
                        "captureId": str(OVERDUE_ID),
                        "title": title_of(OVERDUE_ID),
                        "dueAt": "2026-11-10T00:00:00Z",
                    },
                    {
                        "captureId": str(TODAY_ID),
                        "title": title_of(TODAY_ID),
                        "dueAt": "2026-11-10T11:00:00Z",
                    },
                    {
                        "captureId": str(NO_DEADLINE_ID),
                        "title": title_of(NO_DEADLINE_ID),
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
    digests = FakeDigestRepository(report=make_report())
    captures = FakeCaptureRepository([make_candidate(NO_DEADLINE_ID)])

    await _service(digests, captures).generate_report(UUID(int=100))

    [(_, content, _)] = digests.completed
    assert "本文は、ダイジェストに出さない" not in str(content)


@pytest.mark.asyncio
async def test_generate_daily_report_limits_the_items_to_five() -> None:
    digests = FakeDigestRepository(report=make_report())
    captures = FakeCaptureRepository([make_candidate(UUID(int=n)) for n in range(1, 9)])

    await _service(digests, captures).generate_report(UUID(int=100))

    [(_, content, _)] = digests.completed
    assert len(cast(list[object], content["items"])) == 5


@pytest.mark.asyncio
async def test_generate_daily_report_counts_yesterday_in_the_report_timezone() -> None:
    # 期間の日付が 11-10 なら、昨日は 11-09。東京の 11-09 0 時から 11-10 0 時まで
    digests = FakeDigestRepository(report=make_report(period_start=date(2026, 11, 10)))

    await _service(digests).generate_report(UUID(int=100))

    assert digests.done_calls == [
        (
            TOKYO_USER.user_id,
            datetime(2026, 11, 8, 15, 0, tzinfo=UTC),
            datetime(2026, 11, 9, 15, 0, tzinfo=UTC),
        )
    ]


@pytest.mark.asyncio
async def test_generate_daily_report_without_candidates_completes_with_an_empty_digest() -> None:
    digests = FakeDigestRepository(report=make_report())
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
    digests = FakeDigestRepository(report=make_report(status=status))
    captures = FakeCaptureRepository([make_candidate(NO_DEADLINE_ID)])

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


@pytest.mark.asyncio
async def test_list_reports_reads_the_owner_rows_with_the_query() -> None:
    listed = [make_report()]
    digests = FakeDigestRepository(listed=listed)

    reports = await _service(digests).list_reports(
        ListDigestReportsQuery(
            user_id=TOKYO_USER.user_id, kind="weekly", from_date=date(2026, 11, 1), limit=7
        )
    )

    assert reports == listed
    assert digests.list_calls == [
        {
            "user_id": TOKYO_USER.user_id,
            "kind": "weekly",
            "from_date": date(2026, 11, 1),
            "limit": 7,
        }
    ]


@pytest.mark.asyncio
async def test_retry_report_returns_the_requeued_report() -> None:
    requeued = make_report(status=DIGEST_STATUS_PENDING)
    digests = FakeDigestRepository(requeued=requeued)

    report = await _service(digests).retry_report(TOKYO_USER.user_id, report_id=requeued.id)

    assert report == requeued
    [call] = digests.requeue_calls
    assert call["user_id"] == TOKYO_USER.user_id
    assert call["report_id"] == requeued.id
    # 新しい outbox の id は、行の id と別に発行する
    assert isinstance(call["outbox_id"], UUID)
    assert call["outbox_id"] != requeued.id


@pytest.mark.asyncio
async def test_retry_report_raises_not_found_for_a_missing_report() -> None:
    digests = FakeDigestRepository()

    with pytest.raises(DigestReportNotFoundError):
        await _service(digests).retry_report(TOKYO_USER.user_id, report_id=UUID(int=100))


@pytest.mark.asyncio
async def test_retry_report_hides_a_foreign_report_as_not_found() -> None:
    # 他人の行が failed でも、存在を明かさないため 404 にする
    digests = FakeDigestRepository(report=make_report(status=DIGEST_STATUS_FAILED))

    with pytest.raises(DigestReportNotFoundError):
        await _service(digests).retry_report(NEW_YORK_USER.user_id, report_id=UUID(int=100))


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [DIGEST_STATUS_PENDING, DIGEST_STATUS_READY])
async def test_retry_report_raises_not_retryable_for_a_report_that_is_not_failed(
    status: str,
) -> None:
    digests = FakeDigestRepository(report=make_report(status=status))

    with pytest.raises(DigestReportNotRetryableError):
        await _service(digests).retry_report(TOKYO_USER.user_id, report_id=UUID(int=100))
