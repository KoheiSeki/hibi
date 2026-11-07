import hashlib

from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    Embedding,
)
from hibi.ai.tokens import tokenize_text

CAPTURE_EMBED_FAKE_MODEL = "capture-embed-fake-v1"


class FakeTextEmbedder:
    async def embed_text(self, text: str) -> Embedding:
        if text in ["牛乳を買う", "ミルク"]:
            vector = (1, 0, 0, 0, 0, 0, 0, 0)
        elif text in ["あとで読む記事", "読みもの"]:
            vector = (0, 1, 0, 0, 0, 0, 0, 0)
        elif text in ["ランチ 1200 円"]:
            vector = (0, 0, 1, 0, 0, 0, 0, 0)
        else:
            vector = _hash_vector(text)
        return Embedding(
            vector=vector,
            model=CAPTURE_EMBED_FAKE_MODEL,
            dimensions=CAPTURE_EMBED_DIMENSIONS,
            version=CAPTURE_EMBED_VERSION,
        )


def _hash_vector(text: str) -> tuple[float, ...]:
    counts = [0.0] * CAPTURE_EMBED_DIMENSIONS
    for token in tokenize_text(text):
        counts[_token_index(token)] += 1
    return tuple(counts)


def _token_index(token: str) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % CAPTURE_EMBED_DIMENSIONS
