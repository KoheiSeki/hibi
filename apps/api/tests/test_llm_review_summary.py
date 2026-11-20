import json
from types import SimpleNamespace

import pytest
from hibi.ai.llm_review_summary import LlmReviewSummarizer, SdkReviewClient
from hibi.ai.review_summary import ReviewProviderError, WeeklyReviewInput
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import SecretStr

from hibi.ai.metrics import llm_call_count, reset_llm_call
from hibi.modules.digests.content import WeeklyStats

_REVIEW = WeeklyReviewInput(
    stats=WeeklyStats(captured_count=5, done_count=3, open_count=2, overdue_count=1),
    done_titles=["牛乳を買う", "卵を買う"],
)


class _Timeout(APITimeoutError):
    def __init__(self) -> None:
        Exception.__init__(self, "timeout")


class _Connection(APIConnectionError):
    def __init__(self) -> None:
        Exception.__init__(self, "connection")


class _RateLimit(RateLimitError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limit")


class _ServerError(InternalServerError):
    def __init__(self) -> None:
        Exception.__init__(self, "server error")


class FakeModelClient:
    def __init__(self, result: str | Exception) -> None:
        self._result = result
        self.calls: list[WeeklyReviewInput] = []

    async def complete_json(self, *, review: WeeklyReviewInput) -> str:
        self.calls.append(review)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeAsyncOpenAI:
    def __init__(
        self,
        *,
        result: str | None = None,
        error: Exception | None = None,
        **kwargs: object,
    ) -> None:
        del kwargs
        self._result = result
        self._error = error
        self.create_kwargs: dict[str, object] = {}

    @property
    def chat(self) -> FakeAsyncOpenAI:
        return self

    @property
    def completions(self) -> FakeAsyncOpenAI:
        return self

    async def create(self, **kwargs: object) -> object:
        self.create_kwargs = kwargs
        if self._error is not None:
            raise self._error
        message = SimpleNamespace(content=self._result)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.fixture(autouse=True)
def _reset_llm_calls() -> None:
    reset_llm_call()


@pytest.mark.asyncio
async def test_llm_summarizer_returns_the_summary_and_counts_the_call() -> None:
    client = FakeModelClient(json.dumps({"summary": "先週は 3 件を終わらせました。"}))

    summary = await LlmReviewSummarizer(client).summarize_week(_REVIEW)

    assert summary == "先週は 3 件を終わらせました。"
    assert client.calls == [_REVIEW]
    assert llm_call_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["not-json", "{}", '{"summary": 1}', '{"summary": null}'])
async def test_llm_summarizer_returns_an_empty_summary_for_an_invalid_output(raw: str) -> None:
    # 不正な出力は、空の要約で返す。定型文に直すのは、呼び出し側の normalize_summary
    summary = await LlmReviewSummarizer(FakeModelClient(raw)).summarize_week(_REVIEW)

    assert summary == ""
    assert llm_call_count() == 1


@pytest.mark.asyncio
async def test_llm_summarizer_reraises_a_provider_error() -> None:
    with pytest.raises(ReviewProviderError):
        await LlmReviewSummarizer(FakeModelClient(ReviewProviderError())).summarize_week(_REVIEW)

    assert llm_call_count() == 1


def test_llm_summarizer_reports_the_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_review_summary.get_settings",
        lambda: SimpleNamespace(open_ai_model="review-model", open_ai_api_key=SecretStr("k")),
    )

    assert LlmReviewSummarizer(FakeModelClient("{}")).model_name == "review-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [_Timeout(), _Connection(), _RateLimit(), _ServerError()],
    ids=["timeout", "connection", "rate_limit", "server_error"],
)
async def test_sdk_client_maps_transient_errors_to_review_provider_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_review_summary.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=error, **kwargs),
    )

    with pytest.raises(ReviewProviderError):
        await SdkReviewClient().complete_json(review=_REVIEW)


@pytest.mark.asyncio
async def test_sdk_client_does_not_map_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_review_summary.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=RuntimeError("bad request"), **kwargs),
    )

    with pytest.raises(RuntimeError, match="bad request"):
        await SdkReviewClient().complete_json(review=_REVIEW)


@pytest.mark.asyncio
async def test_sdk_client_returns_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_review_summary.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(result='{"summary":"よくできました"}', **kwargs),
    )

    assert await SdkReviewClient().complete_json(review=_REVIEW) == '{"summary":"よくできました"}'


@pytest.mark.asyncio
async def test_sdk_client_prompt_mentions_json_for_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAsyncOpenAI(result='{"summary":"よくできました"}')
    monkeypatch.setattr("hibi.ai.llm_review_summary.AsyncOpenAI", lambda **kwargs: fake)

    await SdkReviewClient().complete_json(review=_REVIEW)

    assert fake.create_kwargs["response_format"] == {"type": "json_object"}
    messages = list(fake.create_kwargs["messages"])  # type: ignore[call-overload]
    assert any("json" in str(message["content"]).lower() for message in messages)


@pytest.mark.asyncio
async def test_sdk_client_sends_only_the_stats_and_the_done_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAsyncOpenAI(result='{"summary":"よくできました"}')
    monkeypatch.setattr("hibi.ai.llm_review_summary.AsyncOpenAI", lambda **kwargs: fake)

    await SdkReviewClient().complete_json(review=_REVIEW)

    messages = list(fake.create_kwargs["messages"])  # type: ignore[call-overload]
    # system と user の 2 通だけ。user には、集計と、完了したシナリオの題が入る
    assert [message["role"] for message in messages] == ["system", "user"]
    user_content = str(messages[1]["content"])
    for expected in ("牛乳を買う", "卵を買う", "5", "3", "2", "1"):
        assert expected in user_content
