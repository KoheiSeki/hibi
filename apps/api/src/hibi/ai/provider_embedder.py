from typing import Protocol

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    Embedding,
    EmbeddingProviderError,
)
from hibi.core.config import get_settings


class EmbeddingModelClient(Protocol):
    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]: ...


class SdkEmbeddingClient:
    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]:
        client = AsyncOpenAI(
            api_key=get_settings().open_ai_embedding_api_key.get_secret_value(),
            base_url=get_settings().open_ai_embedding_base_url,
            timeout=get_settings().open_ai_timeout_seconds,
            max_retries=0,
        )

        try:
            response = await client.embeddings.create(
                model=model, input=text, dimensions=dimensions
            )
            return list(response.data[0].embedding)
        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as error:
            raise EmbeddingProviderError() from error


class ProviderTextEmbedder:
    def __init__(self, client: EmbeddingModelClient | None = None) -> None:
        self._client = client or SdkEmbeddingClient()

    async def embed_text(self, text: str) -> Embedding:
        model = get_settings().open_ai_embedding_model
        vector = await self._client.create_embedding(
            text=text, model=model, dimensions=CAPTURE_EMBED_DIMENSIONS
        )
        if len(vector) != CAPTURE_EMBED_DIMENSIONS:
            raise EmbeddingProviderError()
        return Embedding(
            vector=tuple(value for value in vector),
            model=model,
            dimensions=CAPTURE_EMBED_DIMENSIONS,
            version=CAPTURE_EMBED_VERSION,
        )
