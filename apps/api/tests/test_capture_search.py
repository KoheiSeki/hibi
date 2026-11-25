from uuid import UUID

import pytest

from hibi.ai.embedding import CAPTURE_EMBED_DIMENSIONS, CAPTURE_EMBED_VERSION, Embedding
from hibi.ai.fake_embedder import CAPTURE_EMBED_FAKE_MODEL, FakeTextEmbedder
from hibi.modules.captures.constants import (
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_PENDING,
)
from hibi.modules.captures.search import (
    SearchDocument,
    rank_capture_by_keyword,
    rank_captures_by_semantic,
)

_OWNER_ID = UUID(int=1)
_OTHER_USER_ID = UUID(int=2)


def _document(
    capture_id: int,
    text: str,
    *,
    user_id: UUID = _OWNER_ID,
    status: str = CAPTURE_STATUS_COMPLETED,
    embedding: Embedding | None = None,
) -> SearchDocument:
    return SearchDocument(
        capture_id=UUID(int=capture_id),
        user_id=user_id,
        status=status,
        text=text,
        embedding=embedding,
    )


async def _embedded(
    capture_id: int,
    text: str,
    *,
    user_id: UUID = _OWNER_ID,
    status: str = CAPTURE_STATUS_COMPLETED,
) -> SearchDocument:
    return _document(
        capture_id,
        text,
        user_id=user_id,
        status=status,
        embedding=await FakeTextEmbedder().embed_text(text),
    )


@pytest.mark.asyncio
async def test_fake_embedder_uses_fixed_vectors_for_known_sentences() -> None:
    embedder = FakeTextEmbedder()

    milk_buy = await embedder.embed_text("牛乳を買う")
    milk = await embedder.embed_text("ミルク")
    article = await embedder.embed_text("あとで読む記事")
    reading = await embedder.embed_text("読みもの")
    lunch = await embedder.embed_text("ランチ 1200 円")

    assert milk_buy.vector == milk.vector == (1, 0, 0, 0, 0, 0, 0, 0)
    assert article.vector == reading.vector == (0, 1, 0, 0, 0, 0, 0, 0)
    assert lunch.vector == (0, 0, 1, 0, 0, 0, 0, 0)
    for embedding in (milk_buy, article, lunch):
        assert embedding.model == CAPTURE_EMBED_FAKE_MODEL
        assert embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
        assert embedding.version == CAPTURE_EMBED_VERSION
        assert len(embedding.vector) == CAPTURE_EMBED_DIMENSIONS


@pytest.mark.asyncio
async def test_fake_embedder_hashes_unknown_text_to_a_stable_vector() -> None:
    embedder = FakeTextEmbedder()

    first = await embedder.embed_text("卵を買う")
    second = await embedder.embed_text("卵を買う")

    assert first == second
    assert len(first.vector) == CAPTURE_EMBED_DIMENSIONS
    assert first.vector != (1, 0, 0, 0, 0, 0, 0, 0)


def test_keyword_search_matches_overlapping_words_only() -> None:
    milk_buy = _document(10, "牛乳を買う")
    documents = [
        milk_buy,
        _document(12, "あとで読む記事"),
        _document(13, "牛乳を買う", status=CAPTURE_STATUS_PENDING),
        _document(14, "牛乳を買う", user_id=_OTHER_USER_ID),
    ]

    assert rank_capture_by_keyword(documents, user_id=_OWNER_ID, query="牛乳") == [
        milk_buy.capture_id
    ]
    assert rank_capture_by_keyword(documents, user_id=_OWNER_ID, query="ミルク") == []
    assert rank_capture_by_keyword(documents, user_id=_OWNER_ID, query="記事") == [UUID(int=12)]


def test_keyword_search_orders_ties_by_capture_id() -> None:
    documents = [
        _document(20, "牛乳を買う"),
        _document(10, "牛乳を買う"),
    ]

    assert rank_capture_by_keyword(documents, user_id=_OWNER_ID, query="牛乳") == [
        UUID(int=10),
        UUID(int=20),
    ]


@pytest.mark.asyncio
async def test_semantic_search_ranks_nearby_vectors() -> None:
    milk_buy = await _embedded(10, "牛乳を買う")
    article = await _embedded(12, "あとで読む記事")
    documents = [
        await _embedded(11, "ランチ 1200 円"),
        await _embedded(13, "牛乳を買う", status=CAPTURE_STATUS_PENDING),
        await _embedded(14, "牛乳を買う", user_id=_OTHER_USER_ID),
        milk_buy,
        article,
    ]
    embedder = FakeTextEmbedder()

    assert await rank_captures_by_semantic(
        documents, user_id=_OWNER_ID, query="ミルク", embedder=embedder
    ) == [milk_buy.capture_id]
    assert await rank_captures_by_semantic(
        documents, user_id=_OWNER_ID, query="読みもの", embedder=embedder
    ) == [article.capture_id]


@pytest.mark.asyncio
async def test_semantic_search_skips_a_different_embedding_version() -> None:
    current = await _embedded(10, "牛乳を買う")
    stale = _document(
        11,
        "牛乳を買う",
        embedding=Embedding(
            vector=(1, 0, 0, 0, 0, 0, 0, 0),
            model=CAPTURE_EMBED_FAKE_MODEL,
            dimensions=CAPTURE_EMBED_DIMENSIONS,
            version="capture-embed-old",
        ),
    )

    assert await rank_captures_by_semantic(
        [stale, current],
        user_id=_OWNER_ID,
        query="ミルク",
        embedder=FakeTextEmbedder(),
    ) == [current.capture_id]


@pytest.mark.asyncio
async def test_semantic_search_orders_ties_by_capture_id() -> None:
    documents = [
        await _embedded(20, "牛乳を買う"),
        await _embedded(10, "牛乳を買う"),
    ]

    assert await rank_captures_by_semantic(
        documents,
        user_id=_OWNER_ID,
        query="ミルク",
        embedder=FakeTextEmbedder(),
    ) == [UUID(int=10), UUID(int=20)]
