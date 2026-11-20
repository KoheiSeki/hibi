import pytest
from hibi.ai.fake_review_summary import FakeReviewSummarizer
from hibi.ai.review_summary import REVIEW_SUMMARY_MODEL_FAKE, WeeklyReviewInput

from hibi.ai.metrics import llm_call_count, reset_llm_call
from hibi.modules.digests.content import WEEKLY_SUMMARY_MAX_LENGTH, WeeklyStats, normalize_summary

_REVIEW = WeeklyReviewInput(
    stats=WeeklyStats(captured_count=5, done_count=3, open_count=2, overdue_count=1),
    done_titles=["牛乳を買う"],
)


@pytest.fixture(autouse=True)
def _reset_llm_calls() -> None:
    reset_llm_call()


@pytest.mark.asyncio
async def test_fake_review_summarizer_counts_each_call() -> None:
    summarizer = FakeReviewSummarizer()

    await summarizer.summarize_week(_REVIEW)
    await summarizer.summarize_week(_REVIEW)

    assert llm_call_count() == 2


@pytest.mark.asyncio
async def test_fake_review_summarizer_returns_a_valid_summary_from_the_stats() -> None:
    summary = await FakeReviewSummarizer().summarize_week(_REVIEW)

    # 同じ入力から、いつも同じ短文。完了の件数を含み、要約として正しい長さに収まる
    assert summary == await FakeReviewSummarizer().summarize_week(_REVIEW)
    assert "3" in summary
    assert len(summary) <= WEEKLY_SUMMARY_MAX_LENGTH
    assert normalize_summary(summary) == summary


def test_fake_review_summarizer_reports_the_fake_model_name() -> None:
    assert FakeReviewSummarizer().model_name == REVIEW_SUMMARY_MODEL_FAKE
