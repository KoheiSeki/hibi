from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from profile_helpers import FakeProfileRepository, as_profile_repository
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import FakeTextEmbedder
from hibi.modules.captures.constants import (
    CAPTURE_SEARCH_MODE_KEYWORD,
    CAPTURE_SEARCH_MODE_SEMANTIC,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_PENDING,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.search import SearchDocument
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    Capture,
    SearchCapturesQuery,
)

_OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
_OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
_NOW = datetime(2026, 10, 18, 14, 2, tzinfo=UTC)


def _capture(capture_id: UUID, raw_text: str, *, user_id: UUID = _OWNER_ID) -> Capture:
    return Capture(
        id=capture_id,
        user_id=user_id,
        raw_text=raw_text,
        status=CAPTURE_STATUS_COMPLETED,
        idempotency_key=str(capture_id),
        request_hash="a" * 64,
        processing_generation=1,
        category="shopping",
        route="shopping",
        urgency="normal",
        confidence=None,
        policy_version=None,
        question_version=None,
        processed_at=_NOW,
        clarification_text=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class FakeSearchRepository:
    def __init__(self, captures: list[Capture], *, statuses: dict[UUID, str] | None = None) -> None:
        self.captures = captures
        self.statuses = statuses or {}
        self.document_calls = 0

    async def list_search_documents(self, user_id: UUID) -> list[SearchDocument]:
        self.document_calls += 1
        documents: list[SearchDocument] = []
        for capture in self.captures:
            status = self.statuses.get(capture.id, capture.status)
            if capture.user_id != user_id or status != CAPTURE_STATUS_COMPLETED:
                continue
            documents.append(
                SearchDocument(
                    capture_id=capture.id,
                    user_id=capture.user_id,
                    status=status,
                    text=capture.raw_text,
                    embedding=await FakeTextEmbedder().embed_text(capture.raw_text),
                )
            )
        return documents

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        wanted = set(capture_ids)
        return [
            capture
            for capture in self.captures
            if capture.id in wanted and capture.user_id == user_id
        ]


def _service(repository: FakeSearchRepository) -> CaptureService:
    return CaptureService(
        cast(AsyncSession, None),
        cast(CaptureRepository, repository),
        FakeCaptureClassifier(),
        FakeClarificationGenerator(),
        FakeTextEmbedder(),
        as_profile_repository(FakeProfileRepository()),
    )


def _query(q: str, *, mode: str = CAPTURE_SEARCH_MODE_KEYWORD) -> SearchCapturesQuery:
    return SearchCapturesQuery(user_id=_OWNER_ID, q=q, mode=mode)


_MILK_ID = UUID(int=1)
_ARTICLE_ID = UUID(int=2)
_LUNCH_ID = UUID(int=3)


def _default_captures() -> list[Capture]:
    return [
        _capture(_MILK_ID, "牛乳を買う"),
        _capture(_ARTICLE_ID, "あとで読む記事"),
        _capture(_LUNCH_ID, "ランチ 1200 円"),
    ]


@pytest.mark.asyncio
async def test_keyword_search_finds_the_matching_capture() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("牛乳"))

    assert [capture.id for capture in found] == [_MILK_ID]


@pytest.mark.asyncio
async def test_keyword_search_does_not_match_a_synonym() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("ミルク"))

    assert found == []


@pytest.mark.asyncio
async def test_keyword_search_finds_the_note() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("記事"))

    assert [capture.id for capture in found] == [_ARTICLE_ID]


@pytest.mark.asyncio
async def test_semantic_search_finds_the_synonym() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(
        _query("ミルク", mode=CAPTURE_SEARCH_MODE_SEMANTIC)
    )

    assert [capture.id for capture in found] == [_MILK_ID]


@pytest.mark.asyncio
async def test_semantic_search_does_not_return_milk_for_a_lunch_query() -> None:
    repository = FakeSearchRepository(_default_captures())

    # 固定ベクトルの本文で引く。単独の「ランチ」はhashで牛乳と同じ次元に落ちる
    found = await _service(repository).search_captures(
        _query("ランチ 1200 円", mode=CAPTURE_SEARCH_MODE_SEMANTIC)
    )

    assert [capture.id for capture in found] == [_LUNCH_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [CAPTURE_SEARCH_MODE_KEYWORD, CAPTURE_SEARCH_MODE_SEMANTIC],
)
async def test_search_skips_unfinished_captures(mode: str) -> None:
    repository = FakeSearchRepository(
        _default_captures(), statuses={_MILK_ID: CAPTURE_STATUS_PENDING}
    )

    found = await _service(repository).search_captures(
        _query("牛乳" if mode == CAPTURE_SEARCH_MODE_KEYWORD else "ミルク", mode=mode)
    )

    assert found == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [CAPTURE_SEARCH_MODE_KEYWORD, CAPTURE_SEARCH_MODE_SEMANTIC],
)
async def test_search_skips_other_owners(mode: str) -> None:
    repository = FakeSearchRepository([_capture(_MILK_ID, "牛乳を買う", user_id=_OTHER_ID)])

    found = await _service(repository).search_captures(
        _query("牛乳" if mode == CAPTURE_SEARCH_MODE_KEYWORD else "ミルク", mode=mode)
    )

    assert found == []


@pytest.mark.asyncio
async def test_search_returns_at_most_twenty_captures() -> None:
    captures = [_capture(UUID(int=index + 10), "牛乳を買う") for index in range(25)]
    repository = FakeSearchRepository(captures)

    found = await _service(repository).search_captures(_query("牛乳"))

    assert len(found) == 20


@pytest.mark.asyncio
async def test_search_returns_an_empty_list_without_candidates() -> None:
    repository = FakeSearchRepository([])

    found = await _service(repository).search_captures(_query("牛乳"))

    assert found == []
    assert repository.document_calls == 1
