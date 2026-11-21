from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

REVIEW_SUMMARY_MODEL_FAKE = "fake-review-summary"


@dataclass(frozen=True, slots=True)
class WeeklyStats:
    """週次レビューに出す、先週の件数の集計。

    LLM にも渡すので、個人の内容を含まない数だけを持つ。

    Attributes:
        captured_count: 先週、記録した Capture の数。0 なら LLM を呼ばない。
        done_count: 先週、完了にしたシナリオの数。
        open_count: 作った時点で、未完了のシナリオの数。
        overdue_count: 作った時点で、期限が過ぎている未完了のシナリオの数。
    """

    captured_count: int
    done_count: int
    open_count: int
    overdue_count: int


@dataclass(frozen=True, slots=True)
class WeeklyReviewInput:
    """週次レビューの要約を作るために、LLM に渡す入力。

    渡すのは、先週の集計と、完了にしたシナリオの題だけ。Capture の本文は、個人の
    内容をそのまま含むので、型に項目を持たせず、渡せないようにしている。題は、
    シナリオを作るときに本文から短くしたもので、要約の材料として足りる。

    Attributes:
        stats: 先週の件数の集計。記録、完了、未完了、期限超過。
        done_titles: 先週、完了にしたシナリオの題。完了にした順で、件数に上限がある。
            無ければ空。
    """

    stats: WeeklyStats
    done_titles: Sequence[str]


@dataclass
class ReviewProviderError(Exception):
    """要約の provider の、一時的な障害。timeout、接続失敗、429、5xx。

    job が再試行し、最後まで失敗したら、行を `review_provider_error` で failed にする。
    """

    pass


class ReviewSummarizer(Protocol):
    """週次レビューの要約を作る port。`DigestService` は、この約束だけを知る。

    実装は、network を使わない `FakeReviewSummarizer` と、LLM を使う
    `LlmReviewSummarizer`。どちらを使うかは `build_review_summarizer` が設定で選ぶ。
    """

    @property
    def model_name(self) -> str:
        """`summary_model` に記録する、要約に使うモデルの名前。"""

        ...

    async def summarize_week(self, review: WeeklyReviewInput) -> str:
        """先週の集計と、完了にした題から、週次レビューの要約を 1 つ作る。

        1 回の呼び出しで、LLM への要求は 1 回だけにする。実装の中で再試行しない。
        再試行は、job の retry に任せる。出力の検証(空、空白、長すぎる)は、呼び出し側の
        `normalize_summary` が行うので、ここでは、受け取った要約を、そのまま返して良い。
        JSON として読めないなど、要約を取り出せないときは、例外にせず空の文字列を返す。

        Args:
            review: 先週の集計と、完了にしたシナリオの題。本文は含まない。

        Returns:
            要約の文。取り出せないときは空の文字列。

        Raises:
            ReviewProviderError: timeout、接続失敗、429、5xx。一時的な障害で、job が
                再試行する。
        """

        ...
