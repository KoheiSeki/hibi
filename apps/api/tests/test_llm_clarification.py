import json
from types import SimpleNamespace

import pytest
from openai import APITimeoutError, RateLimitError

from hibi.ai.classification import CLARIFICATION_FALLBACK_TEXT, ClarificationProviderError
from hibi.ai.llm_clarification import LlmClarificationGenerator, SdkClarificationClient
from hibi.ai.metrics import llm_call_count, reset_llm_call


class _Timeout(APITimeoutError):
    def __init__(self) -> None:
        Exception.__init__(self, "timeout")


class _RateLimit(RateLimitError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limit")


class FakeModelClient:
    def __init__(self, result: str | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, *, text: str, category: str) -> str:
        self.calls.append((text, category))
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
async def test_llm_generator_returns_question_and_counts_the_call() -> None:
    client = FakeModelClient(json.dumps({"question": "いつの予定ですか？"}))  # noqa: RUF001

    question = await LlmClarificationGenerator(client).generate_clarification(
        "牛乳",
        category="shopping",
    )

    assert question == "いつの予定ですか？"  # noqa: RUF001
    assert client.calls == [("牛乳", "shopping")]
    assert llm_call_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "not-json",
        "{}",
        '{"question": 1}',
        '{"question": ""}',
        '{"question": "   "}',
        json.dumps({"question": "あ" * 501}),
    ],
)
async def test_llm_generator_uses_fallback_for_invalid_output(raw: str) -> None:
    question = await LlmClarificationGenerator(FakeModelClient(raw)).generate_clarification(
        "牛乳",
        category="shopping",
    )

    assert question == CLARIFICATION_FALLBACK_TEXT
    assert llm_call_count() == 1


@pytest.mark.asyncio
async def test_llm_generator_keeps_question_at_max_length() -> None:
    expected = "あ" * 500

    question = await LlmClarificationGenerator(
        FakeModelClient(json.dumps({"question": expected}))
    ).generate_clarification("牛乳", category="shopping")

    assert question == expected


@pytest.mark.asyncio
async def test_llm_generator_reraises_provider_error() -> None:
    with pytest.raises(ClarificationProviderError):
        await LlmClarificationGenerator(
            FakeModelClient(ClarificationProviderError())
        ).generate_clarification("牛乳", category="shopping")

    assert llm_call_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [_Timeout(), _RateLimit()],
    ids=["timeout", "rate_limit"],
)
async def test_sdk_client_maps_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_clarification.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=error, **kwargs),
    )

    with pytest.raises(ClarificationProviderError):
        await SdkClarificationClient().complete_json(text="牛乳", category="shopping")


@pytest.mark.asyncio
async def test_sdk_client_does_not_map_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_clarification.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=RuntimeError("bad request"), **kwargs),
    )

    with pytest.raises(RuntimeError, match="bad request"):
        await SdkClarificationClient().complete_json(text="牛乳", category="shopping")


@pytest.mark.asyncio
async def test_sdk_client_returns_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hibi.ai.llm_clarification.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(result='{"question":"いつですか"}', **kwargs),
    )

    assert await SdkClarificationClient().complete_json(text="牛乳", category="shopping") == (
        '{"question":"いつですか"}'
    )


@pytest.mark.asyncio
async def test_sdk_client_prompt_mentions_json_for_json_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeAsyncOpenAI(result='{"question":"いつですか"}')
    monkeypatch.setattr("hibi.ai.llm_clarification.AsyncOpenAI", lambda **kwargs: fake)

    await SdkClarificationClient().complete_json(text="牛乳", category="shopping")

    assert fake.create_kwargs["response_format"] == {"type": "json_object"}
    messages = list(fake.create_kwargs["messages"])  # type: ignore[call-overload]
    assert any("json" in str(message["content"]).lower() for message in messages)
