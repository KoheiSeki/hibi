from types import SimpleNamespace

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from pydantic import SecretStr

from hibi.ai import provider_embedder
from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    EmbeddingProviderError,
)
from hibi.ai.provider_embedder import ProviderTextEmbedder, SdkEmbeddingClient

_MODEL = "text-embedding-3-small"


class _Timeout(APITimeoutError):
    def __init__(self) -> None:
        Exception.__init__(self, "timeout")


class _Connection(APIConnectionError):
    def __init__(self) -> None:
        Exception.__init__(self, "connection")


class _RateLimit(RateLimitError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limit")


class _InternalServer(InternalServerError):
    def __init__(self) -> None:
        Exception.__init__(self, "internal server error")


class FakeEmbeddingClient:
    def __init__(self, result: list[float] | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, str, int]] = []

    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]:
        self.calls.append((text, model, dimensions))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeAsyncOpenAI:
    def __init__(
        self,
        *,
        result: list[float] | None = None,
        error: Exception | None = None,
        **kwargs: object,
    ) -> None:
        del kwargs
        self._result = result
        self._error = error

    @property
    def embeddings(self) -> FakeAsyncOpenAI:
        return self

    async def create(self, **kwargs: object) -> object:
        del kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(data=[SimpleNamespace(embedding=self._result)])


@pytest.fixture(autouse=True)
def _embedding_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_embedder,
        "get_settings",
        lambda: SimpleNamespace(
            open_ai_embedding_api_key=SecretStr("test-key"),
            open_ai_embedding_base_url="",
            open_ai_embedding_model=_MODEL,
            open_ai_timeout_seconds=30.0,
        ),
    )


@pytest.mark.asyncio
async def test_provider_embedder_returns_the_vector_with_fixed_dimensions() -> None:
    client = FakeEmbeddingClient([0.5] * CAPTURE_EMBED_DIMENSIONS)

    embedding = await ProviderTextEmbedder(client).embed_text("牛乳を買う")

    assert embedding.vector == tuple([0.5] * CAPTURE_EMBED_DIMENSIONS)
    assert embedding.model == _MODEL
    assert embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert embedding.version == CAPTURE_EMBED_VERSION
    assert client.calls == [("牛乳を買う", _MODEL, CAPTURE_EMBED_DIMENSIONS)]


@pytest.mark.asyncio
@pytest.mark.parametrize("vector", [[], [0.1] * 7, [0.1] * 9])
async def test_provider_embedder_rejects_other_dimensions(vector: list[float]) -> None:
    with pytest.raises(EmbeddingProviderError):
        await ProviderTextEmbedder(FakeEmbeddingClient(vector)).embed_text("牛乳を買う")


@pytest.mark.asyncio
async def test_provider_embedder_reraises_provider_error() -> None:
    with pytest.raises(EmbeddingProviderError):
        await ProviderTextEmbedder(FakeEmbeddingClient(EmbeddingProviderError())).embed_text(
            "牛乳を買う"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [_Timeout(), _Connection(), _RateLimit(), _InternalServer()],
    ids=["timeout", "connection", "rate_limit", "internal_server"],
)
async def test_sdk_client_maps_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=error, **kwargs),
    )

    with pytest.raises(EmbeddingProviderError):
        await SdkEmbeddingClient().create_embedding(
            text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
        )


@pytest.mark.asyncio
async def test_sdk_client_does_not_map_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=RuntimeError("bad request"), **kwargs),
    )

    with pytest.raises(RuntimeError, match="bad request"):
        await SdkEmbeddingClient().create_embedding(
            text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
        )


@pytest.mark.asyncio
async def test_sdk_client_returns_the_first_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(result=[0.25] * CAPTURE_EMBED_DIMENSIONS, **kwargs),
    )

    vector = await SdkEmbeddingClient().create_embedding(
        text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
    )

    assert vector == [0.25] * CAPTURE_EMBED_DIMENSIONS
