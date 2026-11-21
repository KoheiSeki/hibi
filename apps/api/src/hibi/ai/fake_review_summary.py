from hibi.ai.metrics import record_llm_call
from hibi.ai.review_summary import REVIEW_SUMMARY_MODEL_FAKE, WeeklyReviewInput


class FakeReviewSummarizer:
    """`ReviewSummarizer` の、network を使わない実装。

    `model_name` は `REVIEW_SUMMARY_MODEL_FAKE`。行の `summary_model` に、この名前が
    残るので、fake で作った週次レビューを、あとから見分けられる。
    """

    model_name = REVIEW_SUMMARY_MODEL_FAKE

    async def summarize_week(self, review: WeeklyReviewInput) -> str:
        """集計から、決まった形の短い要約を作る。LLM も network も使わない。

        API キーが無い環境と、通常の pytest で、実 adapter の代わりに使う。呼び出しは、
        実 adapter と同じく `record_llm_call()` で数える。週次レビューで LLM を何回
        呼んだかを、fake のままテストで確かめられるようにするため。

        同じ入力からは、いつも同じ文を返す。題は使わず、件数だけから作るので、要約の
        長さは常に上限より短く、`normalize_summary` で定型文に置き換わることはない。
        一時的な障害を起こさないので、`ReviewProviderError` は送出しない。

        Args:
            review: 先週の集計と、完了にしたシナリオの題。

        Returns:
            件数を埋め込んだ、1 文の要約。
        """

        record_llm_call()

        stats = review.stats
        return (
            f"先週は {stats.captured_count} 件を記録し、{stats.done_count} 件を終えました。"
            f"未完了は {stats.open_count} 件で、そのうち {stats.overdue_count} 件は期限超過です。"
        )
