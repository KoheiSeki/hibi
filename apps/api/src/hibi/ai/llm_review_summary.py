from collections.abc import Iterable
from typing import Protocol

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError
from pydantic.config import ConfigDict

from hibi.ai.metrics import record_llm_call
from hibi.ai.review_summary import ReviewProviderError, WeeklyReviewInput
from hibi.core.config import get_settings


class ReviewOutput(BaseModel):
    """LLM の応答の JSON を、検証してから読むための型。

    形は、system プロンプトで指示した `{"summary":"..."}` と同じにする。プロンプトの
    形を変えるときは、この型も一緒に変える。LLM は指示した以外の項目を足すことが
    あるので、`summary` 以外の項目は無視する(`extra="ignore"`)。足された項目のせいで、
    正しい要約まで捨てないため。

    `summary` が無い、文字列でない、JSON として読めない応答は、`ValidationError` に
    なる。長さと空白の検査はしない。検査は service の `normalize_summary` が行う。

    API のスキーマではない。OpenAPI には出ず、この adapter の中だけで使う。

    Attributes:
        summary: モデルが返した要約。数値や null は文字列に変換せず、不正として扱う。
    """

    model_config = ConfigDict(extra="ignore")
    summary: str


class ReviewModelClient(Protocol):
    """`LlmReviewSummarizer` が使う client の形。テストで fake に差し替えるための型。

    port ではない。実装は同じファイルの `SdkReviewClient` だけで、外部依存を切り離す
    目的はない。テストが、`SdkReviewClient` を継承しない fake を渡しても、型の検査が
    通るようにするために置いている。`llm_clarification.py` の `ClarificationModelClient`
    と同じ形。
    """

    async def complete_json(self, *, review: WeeklyReviewInput) -> str:
        """集計と題をモデルに 1 回送り、応答の本文を、解釈せずに文字列で返す。

        要求は 1 回だけにし、実装の中で再試行しない。再試行は job の retry に任せる。
        応答は `{"summary":"..."}` の JSON を求めるが、形の検証はしない。読めない応答でも
        例外にせず、そのまま返す。検証は `LlmReviewSummarizer` が行う。

        Args:
            review: 先週の集計と、完了にしたシナリオの題。

        Returns:
            モデルが返した本文。本文が無ければ空の文字列。

        Raises:
            ReviewProviderError: timeout、接続失敗、429、5xx。一時的な障害で、job が
                再試行する。
        """

        ...


class SdkReviewClient:
    """OpenAI 互換の API に、週次レビューの要約を要求する client。

    接続先、キー、モデル、timeout は設定から読む。呼び出しのたびに SDK の client を作る。
    """

    async def complete_json(self, *, review: WeeklyReviewInput) -> str:
        """集計と題を OpenAI 互換の API に送り、要約の JSON を、文字列のまま返す。

        `json_object` モードで 1 回だけ要求する。このモードは、プロンプトに `JSON` の語が
        無いと API が拒否するので、system プロンプトに、出力の形 `{"summary":"..."}` と
        500 文字以内であることを書く。user には、集計の件数と、完了にしたシナリオの題
        だけを入れる。Capture の本文は、`review` が持たないので、送りようがない。

        SDK の再試行は切る(`max_retries=0`)。再試行は job の retry に任せる。両方で
        再試行すると、回数が掛け算で増え、障害の間に API へ負荷をかけ続けるため。

        JSON の解釈と、要約の取り出しは、ここでは行わない。`LlmReviewSummarizer` が行う。
        応答の本文が無いときは、空の文字列を返す。

        Args:
            review: 先週の集計と、完了にしたシナリオの題。

        Returns:
            モデルが返した本文。JSON のはずだが、検証していない。無ければ空の文字列。

        Raises:
            ReviewProviderError: timeout、接続失敗、429、5xx。一時的な障害で、job が
                再試行する。それ以外の API の失敗(400 など)は、そのまま送出する。
        """

        client = AsyncOpenAI(
            api_key=get_settings().open_ai_api_key.get_secret_value(),
            base_url=get_settings().open_ai_base_url or None,
            timeout=get_settings().open_ai_timeout_seconds,
            max_retries=0,
        )

        messages: Iterable[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    "先週の記録を、利用者を励ます短い日本語で要約する。"
                    '返答は {"summary":"..."} の形の JSON だけにする。'
                    "summary は500文字以内にする。"
                ),
            },
            {"role": "user", "content": _format_review(review)},
        ]
        try:
            completion = await client.chat.completions.create(
                model=get_settings().open_ai_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            return content if content is not None else ""
        except (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError) as error:
            raise ReviewProviderError() from error


class LlmReviewSummarizer:
    """`ReviewSummarizer` の、OpenAI 互換の API を使う実装。

    HTTP の境界は `ReviewModelClient` に任せ、このクラスは JSON の解釈だけを持つ。
    テストでは、client を fake に差し替えて、network を使わずに確かめる。
    """

    def __init__(self, client: ReviewModelClient | None = None) -> None:
        """要約を要求する client を受け取る。

        Args:
            client: 要約を要求する client。None なら `SdkReviewClient` を使う。
        """

        self._client = client or SdkReviewClient()

    @property
    def model_name(self) -> str:
        """`summary_model` に記録する、設定のモデル名。

        要求に使うモデルと同じ値を、読むたびに設定から返す。
        """

        return get_settings().open_ai_model

    async def summarize_week(self, review: WeeklyReviewInput) -> str:
        """集計と題を LLM に 1 回送り、返ってきた JSON から要約を取り出す。

        呼び出しは、要求の前に `record_llm_call()` で数える。要求が失敗しても数えるので、
        障害の間に何回 LLM を呼ぼうとしたかが、回数に残る。

        応答が JSON として読めない、または `summary` が文字列でないときは、再試行せず、
        空の文字列を返す。spec は、structured output の不正を再試行しないと決めている。
        空の文字列は、service の `normalize_summary` が定型文に置き換えるので、この
        クラスは定型文を知らない。読めた `summary` は、長さや空白を検査せず、そのまま返す。
        検査も `normalize_summary` の 1 か所で行う。

        Args:
            review: 先週の集計と、完了にしたシナリオの題。

        Returns:
            取り出した要約。取り出せないときは空の文字列。

        Raises:
            ReviewProviderError: timeout、接続失敗、429、5xx。client が送出したものを、
                そのまま上げる。job が再試行する。
        """

        record_llm_call()
        raw = await self._client.complete_json(review=review)
        return _summary_from_output(raw)


def _format_review(review: WeeklyReviewInput) -> str:
    """集計と題を、user のメッセージに入れる、1 項目 1 行の文にする。

    件数はラベル付きで並べ、題は 1 行に 1 つ、`- ` を付けて並べる。モデルが、件数と題を
    取り違えないようにするため。題が無い週は、題の行の代わりに「なし」と書き、空の
    見出しだけが残って、モデルが続きを補おうとしないようにする。

    題は、利用者が書いた本文から作るので、指示のような文を含み得る。題は見出しの下に
    並べるだけにして、system の指示とは別のメッセージに置く。

    Args:
        review: 先週の集計と、完了にしたシナリオの題。

    Returns:
        user のメッセージの本文。
    """

    stats = review.stats
    lines = [
        f"記録した件数: {stats.captured_count}",
        f"完了した件数: {stats.done_count}",
        f"未完了の件数: {stats.open_count}",
        f"期限を過ぎた件数: {stats.overdue_count}",
        "完了したことの題:",
    ]
    lines += [f"- {title}" for title in review.done_titles] or ["なし"]
    return "\n".join(lines)


def _summary_from_output(raw: str) -> str:
    """応答の JSON から要約を取り出す。取り出せなければ空の文字列を返す。

    読み込みと検証は `ReviewOutput` に任せる。JSON として読めない、一番外側が
    オブジェクトでない、`summary` が無い、文字列でない応答は、例外にせず空にする。
    例外にすると job が再試行してしまうが、spec は不正な出力を再試行しないと決めている。
    空の文字列は、service の `normalize_summary` が定型文に置き換える。

    Args:
        raw: モデルが返した本文。

    Returns:
        要約。取り出せなければ空の文字列。
    """

    try:
        return ReviewOutput.model_validate_json(raw).summary
    except ValidationError:
        return ""
