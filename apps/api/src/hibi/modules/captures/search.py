from collections.abc import Sequence
from dataclasses import dataclass
from math import log
from uuid import UUID

import numpy as np

from hibi.ai.embedding import Embedding, TextEmbedder
from hibi.ai.tokens import tokenize_text
from hibi.modules.captures.types import CAPTURE_STATUS_COMPLETED


@dataclass(frozen=True, slots=True)
class SearchDocument:
    capture_id: UUID
    user_id: UUID
    status: str
    text: str
    embedding: Embedding | None = None


def rank_capture_by_keyword(
    documents: Sequence[SearchDocument], *, user_id: UUID, query: str
) -> list[UUID]:
    query_tokens = tokenize_text(query)
    if not query_tokens:
        return []

    candidates = [
        (document.capture_id, tokenize_text(document.text))
        for document in documents
        if document.user_id == user_id and document.status == CAPTURE_STATUS_COMPLETED
    ]
    corpus: list[list[str]] = [tokens for _, tokens in candidates]
    scored = [
        (capture_id, _tf_idf_score(query_tokens, document_tokens, corpus))
        for capture_id, document_tokens in candidates
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))

    return [capture_id for capture_id, score in scored if score > 0]


async def rank_captures_by_semantic(
    documents: Sequence[SearchDocument], *, user_id: UUID, query: str, embedder: TextEmbedder
) -> list[UUID]:
    # queryをベクトル変換
    embed_query = await embedder.embed_text(query)

    candidates = [
        document
        for document in documents
        if document.user_id == user_id and document.status == CAPTURE_STATUS_COMPLETED
    ]
    cosine_similarities = [
        (
            candidate.capture_id,
            _cosine_similarity(list(embed_query.vector), list(candidate.embedding.vector)),
        )
        for candidate in candidates
        if candidate.embedding is not None and candidate.embedding.version == embed_query.version
    ]
    cosine_similarities.sort(key=lambda item: (-item[1], item[0]))

    return [
        capture_id for capture_id, cosine_similarity in cosine_similarities if cosine_similarity > 0
    ]


def _tf_idf_score(
    query_tokens: list[str], document_tokens: list[str], corpus: list[list[str]]
) -> float:
    if not document_tokens:
        return 0.0

    tf_by_token: dict[str, float] = {
        token: _term_count(token, document_tokens) for token in query_tokens
    }
    score = 0.0
    for token in query_tokens:
        idf = log((1 + len(corpus)) / (1 + _document_frequency(token, corpus))) + 1
        score += tf_by_token[token] * idf

    return score


def _term_count(token: str, document_tokens: list[str]) -> int:
    return document_tokens.count(token)


def _document_frequency(token: str, corpus: list[list[str]]) -> int:
    return sum(token in document_tokens for document_tokens in corpus)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))
