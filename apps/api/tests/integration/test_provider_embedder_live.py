import pytest

from hibi.ai.embedding import CAPTURE_EMBED_DIMENSIONS, CAPTURE_EMBED_VERSION
from hibi.ai.provider_embedder import ProviderTextEmbedder
from hibi.core.config import get_settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_embedder_returns_a_vector() -> None:
    if not get_settings().open_ai_embedding_api_key.get_secret_value().strip():
        pytest.skip("HIBI_OPEN_AI_EMBEDDING_API_KEY is not configured")

    embedding = await ProviderTextEmbedder().embed_text("牛乳を買う")

    assert embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert len(embedding.vector) == CAPTURE_EMBED_DIMENSIONS
    assert embedding.version == CAPTURE_EMBED_VERSION
    assert any(value != 0.0 for value in embedding.vector)
