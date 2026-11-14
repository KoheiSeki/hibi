from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

import pytest
from profile_helpers import FakeProfileRepository, as_profile_repository
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import FakeTextEmbedder
from hibi.modules.captures.errors import CaptureNotFoundError
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.today import TodayCandidate
from hibi.modules.captures.types import (
    CAPTURE_STATUS_COMPLETED,
    Capture,
    TodayCapturesQuery,
)

_OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
# 2026-11-10 15:00 JST
_NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
_CREATED = datetime(2026, 11, 1, tzinfo=UTC)

_NO_DEADLINE_ID = UUID(int=1)
_OVERDUE_ID = UUID(int=2)
_TODAY_ID = UUID(int=3)
_TOMORROW_ID = UUID(int=4)


def _capture(capture_id: UUID) -> Capture:
    return Capture(
        id=capture_id,
        user_id=_OWNER_ID,
        raw_text="牛乳を買う",
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
        processed_at=_CREATED,
        clarification_text=None,
        created_at=_CREATED,
        updated_at=_CREATED,
    )


def _candidate(capture_id: UUID, *, due_at: datetime | None = None) -> TodayCandidate:
    return TodayCandidate(
        capture_id=capture_id,
        urgency_score=Decimal("0.50"),
        due_at=due_at,
        created_at=_CREATED,
    )


_OVERDUE = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)  # 09:00 JST
_LATER_TODAY = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)  # 20:00 JST
_TOMORROW = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)  # 09:00 JST 翌日


class FakeTodayRepository:
    def __init__(self, candidates: list[TodayCandidate], *, scenario_found: bool = True) -> None:
        self.candidates = candidates
        self.scenario_found = scenario_found
        self.by_ids_calls: list[list[UUID]] = []
        self.done_calls: list[tuple[UUID, UUID, bool]] = []

    async def list_today_candidates(self, user_id: UUID) -> list[TodayCandidate]:
        assert user_id == _OWNER_ID
        return self.candidates

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        assert user_id == _OWNER_ID
        self.by_ids_calls.append(list(capture_ids))
        # 順位の逆順で返し、service が順位どおりに並べ直すことを確かめる
        return [_capture(capture_id) for capture_id in reversed(capture_ids)]

    async def set_scenario_done(self, user_id: UUID, *, capture_id: UUID, done: bool) -> bool:
        self.done_calls.append((user_id, capture_id, done))
        return self.scenario_found

    async def get_by_id(self, user_id: UUID, *, capture_id: UUID) -> Capture | None:
        assert user_id == _OWNER_ID
        return _capture(capture_id)


def _service(
    repository: FakeTodayRepository, profiles: FakeProfileRepository | None = None
) -> CaptureService:
    return CaptureService(
        cast(AsyncSession, None),
        cast(CaptureRepository, repository),
        FakeCaptureClassifier(),
        FakeClarificationGenerator(),
        FakeTextEmbedder(),
        as_profile_repository(profiles or FakeProfileRepository("Asia/Tokyo")),
        clock=lambda: _NOW,
    )


def _query(limit: int = 5) -> TodayCapturesQuery:
    return TodayCapturesQuery(user_id=_OWNER_ID, limit=limit)


@pytest.mark.asyncio
async def test_today_returns_captures_in_priority_order() -> None:
    repository = FakeTodayRepository(
        [
            _candidate(_NO_DEADLINE_ID),
            _candidate(_OVERDUE_ID, due_at=_OVERDUE),
            _candidate(_TODAY_ID, due_at=_LATER_TODAY),
        ]
    )

    captures = await _service(repository).list_today_captures(_query())

    assert [capture.id for capture in captures] == [_OVERDUE_ID, _TODAY_ID, _NO_DEADLINE_ID]


@pytest.mark.asyncio
async def test_today_drops_candidates_due_after_the_end_of_the_local_day() -> None:
    repository = FakeTodayRepository(
        [_candidate(_NO_DEADLINE_ID), _candidate(_TOMORROW_ID, due_at=_TOMORROW)]
    )

    captures = await _service(repository).list_today_captures(_query())

    assert [capture.id for capture in captures] == [_NO_DEADLINE_ID]
    assert repository.by_ids_calls == [[_NO_DEADLINE_ID]]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("timezone", "expected"),
    [
        # 11/10 20:00 UTC は、JST では 11/11 05:00 なので明日の扱い
        ("Asia/Tokyo", []),
        ("UTC", [_TODAY_ID]),
        # 不正な名前は UTC として扱い、例外にしない
        ("Not/AZone", [_TODAY_ID]),
    ],
)
async def test_today_uses_the_timezone_of_the_owner(timezone: str, expected: list[UUID]) -> None:
    due = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
    repository = FakeTodayRepository([_candidate(_TODAY_ID, due_at=due)])
    profiles = FakeProfileRepository(timezone)

    captures = await _service(repository, profiles).list_today_captures(_query())

    assert [capture.id for capture in captures] == expected
    assert profiles.lookups == [_OWNER_ID]


@pytest.mark.asyncio
async def test_today_applies_the_limit() -> None:
    repository = FakeTodayRepository([_candidate(UUID(int=n)) for n in range(1, 8)])

    captures = await _service(repository).list_today_captures(_query(limit=3))

    assert [capture.id for capture in captures] == [UUID(int=1), UUID(int=2), UUID(int=3)]


@pytest.mark.asyncio
async def test_today_returns_an_empty_list_without_candidates() -> None:
    repository = FakeTodayRepository([])

    captures = await _service(repository).list_today_captures(_query())

    assert captures == []
    assert repository.by_ids_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("done", [True, False])
async def test_set_scenario_done_updates_the_scenario_and_returns_the_capture(
    done: bool,
) -> None:
    repository = FakeTodayRepository([])

    capture = await _service(repository).set_capture_scenario_done(_OWNER_ID, _TODAY_ID, done=done)

    assert capture.id == _TODAY_ID
    assert repository.done_calls == [(_OWNER_ID, _TODAY_ID, done)]


@pytest.mark.asyncio
async def test_set_scenario_done_raises_not_found_without_a_scenario() -> None:
    repository = FakeTodayRepository([], scenario_found=False)

    with pytest.raises(CaptureNotFoundError):
        await _service(repository).set_capture_scenario_done(_OWNER_ID, _TODAY_ID, done=True)
