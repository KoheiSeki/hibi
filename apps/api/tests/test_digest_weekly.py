from dataclasses import fields
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID

import pytest
from digest_helpers import (
    TOKYO_USER,
    FakeCaptureRepository,
    FakeDigestRepository,
    FakeSummarizer,
    make_candidate,
    make_report,
)

from hibi.ai.review_summary import ReviewProviderError, ReviewSummarizer, WeeklyReviewInput
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.content import (
    EMPTY_WEEK_SUMMARY,
    SUMMARY_FALLBACK_TEXT,
    WeeklyStats,
)
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.service import DigestService
from hibi.modules.digests.types import DIGEST_KIND_WEEKLY

# 2026-11-09 は月曜。東京は 09:00。先週は 11-02 の月曜から 11-08 の日曜まで
_MONDAY = datetime(2026, 11, 9, 0, 0, tzinfo=UTC)
_PERIOD_START = date(2026, 11, 2)
_WEEK_START = datetime(2026, 11, 1, 15, 0, tzinfo=UTC)  # 11-02 0 時 JST
_WEEK_END = datetime(2026, 11, 8, 15, 0, tzinfo=UTC)  # 11-09 0 時 JST
_REPORT_ID = UUID(int=100)

_OVERDUE_DUE = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)


def _weekly_report():
    return make_report(kind=DIGEST_KIND_WEEKLY, period_start=_PERIOD_START)


def _service(
    digests: FakeDigestRepository,
    captures: FakeCaptureRepository,
    summarizer: FakeSummarizer,
) -> DigestService:
    return DigestService(
        digests=cast(DigestRepository, digests),
        captures=cast(CaptureRepository, captures),
        summarizer=cast(ReviewSummarizer, summarizer),
        clock=lambda: _MONDAY,
    )


@pytest.mark.asyncio
async def test_weekly_report_calls_the_summarizer_once_with_titles_only() -> None:
    digests = FakeDigestRepository(
        report=_weekly_report(),
        captured_count=5,
        done_count=3,
        done_titles=["牛乳を買う", "卵を買う"],
    )
    # 未完了は 2 件で、期限が過ぎているのは 1 件
    captures = FakeCaptureRepository(
        [make_candidate(UUID(int=1), due_at=_OVERDUE_DUE), make_candidate(UUID(int=2))]
    )
    summarizer = FakeSummarizer("先週は 3 件を終わらせました。", model_name="test-model")

    await _service(digests, captures, summarizer).generate_report(_REPORT_ID)

    [review] = summarizer.calls
    assert review.stats == WeeklyStats(
        captured_count=5, done_count=3, open_count=2, overdue_count=1
    )
    assert list(review.done_titles) == ["牛乳を買う", "卵を買う"]
    # 本文を持つ Capture は、読まない。LLM に渡すのは、集計と完了したシナリオの題だけ
    assert captures.by_ids_calls == []
    assert digests.completed == [
        (
            _REPORT_ID,
            {
                "stats": {
                    "capturedCount": 5,
                    "doneCount": 3,
                    "openCount": 2,
                    "overdueCount": 1,
                },
                "summary": "先週は 3 件を終わらせました。",
            },
            "test-model",
        )
    ]
    assert digests.failed == []


@pytest.mark.asyncio
async def test_weekly_report_reads_the_week_in_the_report_timezone() -> None:
    # 期間の日付が 11-02 なら、東京の 11-02 0 時から、翌週の 11-09 0 時まで
    digests = FakeDigestRepository(report=_weekly_report(), captured_count=1)
    summarizer = FakeSummarizer()

    await _service(digests, FakeCaptureRepository(), summarizer).generate_report(_REPORT_ID)

    user_id = TOKYO_USER.user_id
    assert digests.captured_calls == [(user_id, _WEEK_START, _WEEK_END)]
    assert digests.done_calls == [(user_id, _WEEK_START, _WEEK_END)]
    [(title_user, title_start, title_end, _limit)] = digests.title_calls
    assert (title_user, title_start, title_end) == (user_id, _WEEK_START, _WEEK_END)


@pytest.mark.asyncio
async def test_weekly_report_for_an_empty_week_does_not_call_the_summarizer() -> None:
    digests = FakeDigestRepository(report=_weekly_report(), captured_count=0)
    summarizer = FakeSummarizer()

    await _service(digests, FakeCaptureRepository(), summarizer).generate_report(_REPORT_ID)

    assert summarizer.calls == []
    [(report_id, content, summary_model)] = digests.completed
    assert report_id == _REPORT_ID
    assert content["summary"] == EMPTY_WEEK_SUMMARY
    # LLM を使っていないので、モデル名は記録しない
    assert summary_model is None


@pytest.mark.asyncio
@pytest.mark.parametrize("summary", ["", "   ", "あ" * 501], ids=["empty", "blank", "too_long"])
async def test_weekly_report_uses_the_fallback_for_an_invalid_summary(summary: str) -> None:
    digests = FakeDigestRepository(report=_weekly_report(), captured_count=2)
    summarizer = FakeSummarizer(summary)

    await _service(digests, FakeCaptureRepository(), summarizer).generate_report(_REPORT_ID)

    # 不正な要約は、再試行せず、定型文で ready にする
    assert len(summarizer.calls) == 1
    [(_, content, _)] = digests.completed
    assert content["summary"] == SUMMARY_FALLBACK_TEXT
    assert digests.failed == []


@pytest.mark.asyncio
async def test_weekly_report_keeps_a_summary_at_the_maximum_length() -> None:
    digests = FakeDigestRepository(report=_weekly_report(), captured_count=2)
    summary = "あ" * 500

    await _service(digests, FakeCaptureRepository(), FakeSummarizer(summary)).generate_report(
        _REPORT_ID
    )

    [(_, content, _)] = digests.completed
    assert content["summary"] == summary


@pytest.mark.asyncio
async def test_weekly_report_reraises_a_provider_error_for_the_job_to_retry() -> None:
    digests = FakeDigestRepository(report=_weekly_report(), captured_count=2)
    summarizer = FakeSummarizer(ReviewProviderError())

    with pytest.raises(ReviewProviderError):
        await _service(digests, FakeCaptureRepository(), summarizer).generate_report(_REPORT_ID)

    # 失敗の確定は、最終試行を知っている job の責務。service は ready にも failed にもしない
    assert digests.completed == []
    assert digests.failed == []


@pytest.mark.asyncio
async def test_weekly_report_does_nothing_unless_pending() -> None:
    report = make_report(kind=DIGEST_KIND_WEEKLY, status="ready", period_start=_PERIOD_START)
    digests = FakeDigestRepository(report=report, captured_count=2)
    summarizer = FakeSummarizer()

    await _service(digests, FakeCaptureRepository(), summarizer).generate_report(_REPORT_ID)

    assert summarizer.calls == []
    assert digests.completed == []


def test_the_review_input_carries_stats_and_titles_only() -> None:
    review = WeeklyReviewInput(
        stats=WeeklyStats(captured_count=1, done_count=1, open_count=0, overdue_count=0),
        done_titles=["牛乳を買う"],
    )

    # slots=True の dataclass は __dict__ を持たないので、vars() ではなく fields() で項目を読む
    assert {field.name for field in fields(review)} == {"stats", "done_titles"}
