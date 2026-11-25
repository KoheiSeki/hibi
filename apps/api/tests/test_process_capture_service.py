from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4, uuid7

import pytest
from profile_helpers import FakeProfileRepository, as_profile_repository
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.classification import (
    CAPTURE_QUESTION_VERSION,
    CLARIFICATION_FALLBACK_TEXT,
    ClarificationProviderError,
    Classification,
    ClassificationTimeoutError,
)
from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    Embedding,
)
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import CAPTURE_EMBED_FAKE_MODEL, FakeTextEmbedder
from hibi.ai.metrics import llm_call_count, reset_llm_call
from hibi.modules.captures.constants import (
    CAPTURE_SCENARIO_STATUS_PROPOSED,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
)
from hibi.modules.captures.policies import (
    CAPTURE_ROUTE_POLICY_VERSION,
    CAPTURE_SCENARIO_POLICY_VERSION,
    ScenarioProposal,
    propose_capture_scenario,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    Capture,
)

# 2026-11-10 15:00 JST
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)

# urgency_score が渡されなかったことを、範囲外で保存しない None と区別する
_NOT_PASSED = Decimal("-1")


class FakeProcessCaptureRepository:
    def __init__(
        self,
        capture: Capture | None,
        *,
        allow_start: bool = True,
        fail_processing: bool = False,
        has_embedding: bool = False,
    ) -> None:
        self.capture = capture
        self.allow_start = allow_start
        self.fail_processing = fail_processing
        self.has_embedding = has_embedding
        self.urgency_scores: list[Decimal | None] = []
        self.transitions: list[tuple[str, str]] = []
        self.classifications: list[dict[str, object]] = []
        self.scenario: ScenarioProposal | None = None
        self.embedding: Embedding | None = None
        self.embedding_lookups: list[tuple[UUID, str]] = []

    async def has_same_content_embedding(
        self, user_id: UUID, *, capture_id: UUID, text: str
    ) -> bool:
        del user_id
        self.embedding_lookups.append((capture_id, text))
        return self.has_embedding

    async def get_by_capture_id(self, capture_id: UUID) -> Capture | None:
        if self.capture is None or self.capture.id != capture_id:
            return None
        return self.capture

    async def update_processing_status(
        self,
        *,
        capture_id: UUID,
        processing_generation: int,
        expected_status: str,
        status: str,
    ) -> bool:
        self.transitions.append((expected_status, status))
        if expected_status == CAPTURE_STATUS_PENDING and not self.allow_start:
            return False
        if (
            self.capture is None
            or self.capture.id != capture_id
            or self.capture.processing_generation != processing_generation
            or self.capture.status != expected_status
        ):
            return False
        self.capture = replace(self.capture, status=status)
        return True

    async def complete_capture_classification(
        self,
        *,
        capture_id: UUID,
        processing_generation: int,
        category: str,
        route: str,
        urgency: str,
        confidence: Decimal,
        policy_version: str,
        question_version: str,
        clarification_text: str | None = None,
        urgency_score: Decimal | None = _NOT_PASSED,
        scenario: ScenarioProposal | None = None,
        embedding: Embedding | None = None,
    ) -> Capture | None:
        if self.fail_processing:
            raise RuntimeError("temporary processing failure")
        if (
            self.capture is None
            or self.capture.id != capture_id
            or self.capture.processing_generation != processing_generation
            or self.capture.status != CAPTURE_STATUS_PROCESSING
        ):
            return None
        self.classifications.append(
            {
                "category": category,
                "route": route,
                "urgency": urgency,
                "confidence": confidence,
                "policy_version": policy_version,
                "question_version": question_version,
                "clarification_text": clarification_text,
            }
        )
        self.capture = replace(
            self.capture,
            status=CAPTURE_STATUS_COMPLETED,
            category=category,
            route=route,
            urgency=urgency,
            confidence=confidence,
            policy_version=policy_version,
            question_version=question_version,
            processed_at=datetime.now(UTC),
            clarification_text=clarification_text,
        )
        self.urgency_scores.append(urgency_score)
        self.scenario = scenario
        self.embedding = embedding
        return self.capture


class RecordingEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed_text(self, text: str) -> Embedding:
        self.texts.append(text)
        return await FakeTextEmbedder().embed_text(text)


class RecordingClassifier:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def classify_capture(self, text: str, *, question_version: str) -> Classification:
        self.texts.append(text)
        return Classification(
            category="shopping",
            confidence=Decimal("0.9"),
            urgency_score=0.5,
            question_version=question_version,
        )


class ScriptedClassifier:
    def __init__(self, result: Classification | Exception) -> None:
        self._result = result

    async def classify_capture(self, text: str, *, question_version: str) -> Classification:
        del text, question_version
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class ScriptedGenerator:
    def __init__(self, result: str | Exception) -> None:
        self._result = result

    async def generate_clarification(self, text: str, *, category: str) -> str:
        del text, category
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _low_confidence_classifier() -> ScriptedClassifier:
    return ScriptedClassifier(
        Classification(
            category="shopping",
            confidence=Decimal("0.69"),
            urgency_score=0.5,
            question_version=CAPTURE_QUESTION_VERSION,
        )
    )


def _capture(
    *,
    status: str = CAPTURE_STATUS_PENDING,
    generation: int = 1,
    raw_text: str = "牛乳を買う",
) -> Capture:
    now = datetime.now(UTC)
    return Capture(
        id=uuid7(),
        user_id=uuid4(),
        raw_text=raw_text,
        status=status,
        idempotency_key=str(uuid4()),
        request_hash="a" * 64,
        processing_generation=generation,
        category=None,
        route=None,
        urgency=None,
        confidence=None,
        policy_version=None,
        question_version=None,
        processed_at=None,
        clarification_text=None,
        created_at=now,
        updated_at=now,
    )


def _service(
    repository: FakeProcessCaptureRepository,
    classifier: RecordingClassifier | ScriptedClassifier | FakeCaptureClassifier | None = None,
    generator: ScriptedGenerator | FakeClarificationGenerator | None = None,
    embedder: RecordingEmbedder | FakeTextEmbedder | None = None,
    profiles: FakeProfileRepository | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> CaptureService:
    extra: dict[str, Callable[[], datetime]] = {} if clock is None else {"clock": clock}
    return CaptureService(
        cast(AsyncSession, None),
        cast(CaptureRepository, repository),
        classifier or FakeCaptureClassifier(),
        generator or FakeClarificationGenerator(),
        embedder or FakeTextEmbedder(),
        as_profile_repository(profiles or FakeProfileRepository()),
        **extra,
    )


@pytest.mark.asyncio
async def test_process_capture_saves_classification_when_completed() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    classifier = RecordingClassifier()

    await _service(repository, classifier).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.category == "shopping"
    assert repository.capture.route == "shopping"
    assert repository.capture.urgency == "normal"
    assert repository.capture.confidence == Decimal("0.9")
    assert repository.capture.policy_version == CAPTURE_ROUTE_POLICY_VERSION
    assert repository.capture.question_version == CAPTURE_QUESTION_VERSION
    assert repository.capture.processed_at is not None
    assert classifier.texts == ["牛乳を買う"]
    assert repository.transitions == [
        (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_PROCESSING),
    ]


@pytest.mark.asyncio
async def test_process_capture_keeps_low_confidence_category_and_clarifies_route() -> None:
    reset_llm_call()
    capture = _capture(raw_text="境界未満の牛乳")
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.category == "shopping"
    assert repository.capture.route == "clarify"
    assert repository.capture.confidence == Decimal("0.69")
    assert repository.capture.clarification_text == "それはいつ買いますか？"  # noqa: RUF001
    assert repository.scenario is None
    assert llm_call_count() == 1


@pytest.mark.asyncio
async def test_process_capture_does_not_generate_clarification_for_high_confidence() -> None:
    reset_llm_call()
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository, RecordingClassifier()).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.route == "shopping"
    assert repository.capture.clarification_text is None
    assert llm_call_count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_text", "route", "title", "amount", "remind_text"),
    [
        ("牛乳を買う", "shopping", "牛乳", None, None),
        ("明日の 9 時に起こして", "reminder", "起こして", None, "明日の 9 時"),
        ("ランチ 1200 円", "expense", "ランチ", 1200, None),
    ],
)
async def test_process_capture_proposes_scenario_for_confirmed_routes(
    raw_text: str,
    route: str,
    title: str,
    amount: int | None,
    remind_text: str | None,
) -> None:
    reset_llm_call()
    capture = _capture(raw_text=raw_text)
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.route == route
    assert repository.scenario is not None
    assert repository.scenario.status == CAPTURE_SCENARIO_STATUS_PROPOSED
    assert repository.scenario.title == title
    assert repository.scenario.amount == amount
    assert repository.scenario.remind_text == remind_text
    assert llm_call_count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_text", "route"),
    [
        ("あとで読む記事", "note"),
        ("今日どうだった", "chat"),
    ],
)
async def test_process_capture_does_not_propose_scenario_for_note_or_chat(
    raw_text: str,
    route: str,
) -> None:
    capture = _capture(raw_text=raw_text)
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.route == route
    assert repository.scenario is None


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["timeout", "rate_limit"])
async def test_process_capture_reraises_clarification_provider_error(source: str) -> None:
    assert source in {"timeout", "rate_limit"}
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    with pytest.raises(ClarificationProviderError):
        await _service(
            repository,
            _low_confidence_classifier(),
            ScriptedGenerator(ClarificationProviderError()),
        ).process_capture(capture.id, 1)

    assert repository.classifications == []
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_PROCESSING


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["", "あ" * 501])
async def test_process_capture_stores_fallback_for_invalid_clarification(output: str) -> None:
    reset_llm_call()
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    await _service(
        repository,
        _low_confidence_classifier(),
        ScriptedGenerator(output),
    ).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.route == "clarify"
    assert repository.capture.category == "shopping"
    assert repository.capture.confidence == Decimal("0.69")
    assert repository.capture.clarification_text == CLARIFICATION_FALLBACK_TEXT
    assert llm_call_count() == 0


@pytest.mark.asyncio
async def test_process_capture_keeps_clarification_at_max_length() -> None:
    question = "あ" * 500
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    await _service(
        repository,
        _low_confidence_classifier(),
        ScriptedGenerator(question),
    ).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.clarification_text == question


@pytest.mark.asyncio
async def test_process_capture_reraises_classification_timeout() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    classifier = ScriptedClassifier(ClassificationTimeoutError())

    with pytest.raises(ClassificationTimeoutError):
        await _service(repository, classifier).process_capture(capture.id, 1)

    assert repository.classifications == []
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_PROCESSING


@pytest.mark.asyncio
async def test_process_capture_completes_invalid_schema_as_clarification() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    classifier = ScriptedClassifier(
        Classification(
            category="unknown",
            confidence=Decimal("0.9"),
            urgency_score=0.5,
            question_version=CAPTURE_QUESTION_VERSION,
        )
    )

    await _service(repository, classifier).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.capture.category == "chat"
    assert repository.capture.route == "clarify"
    assert repository.capture.confidence == Decimal("0")
    assert repository.capture.question_version == CAPTURE_QUESTION_VERSION


@pytest.mark.asyncio
async def test_process_capture_stops_when_pending_claim_fails() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, allow_start=False)
    classifier = RecordingClassifier()

    await _service(repository, classifier).process_capture(capture.id, 1)

    assert classifier.texts == []
    assert repository.classifications == []
    assert repository.transitions == [(CAPTURE_STATUS_PENDING, CAPTURE_STATUS_PROCESSING)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("capture", "processing_generation"),
    [
        (None, 1),
        (_capture(generation=2), 1),
        (_capture(status=CAPTURE_STATUS_COMPLETED), 1),
        (_capture(status=CAPTURE_STATUS_FAILED), 1),
    ],
)
async def test_process_capture_ignores_inapplicable_job(
    capture: Capture | None, processing_generation: int
) -> None:
    repository = FakeProcessCaptureRepository(capture)
    classifier = RecordingClassifier()
    capture_id = capture.id if capture is not None else uuid7()

    await _service(repository, classifier).process_capture(capture_id, processing_generation)

    assert classifier.texts == []
    assert repository.classifications == []
    assert repository.transitions == []


@pytest.mark.asyncio
async def test_process_capture_reraises_processing_failure() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, fail_processing=True)

    with pytest.raises(RuntimeError, match="temporary processing failure"):
        await _service(repository).process_capture(capture.id, 1)

    assert repository.classifications == []
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_PROCESSING
    assert repository.transitions == [
        (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_PROCESSING),
    ]


@pytest.mark.asyncio
async def test_mark_processing_failed_transitions_pending_to_failed() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).mark_processing_failed(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_FAILED
    assert repository.transitions[-1] == (
        CAPTURE_STATUS_PENDING,
        CAPTURE_STATUS_FAILED,
    )


@pytest.mark.asyncio
async def test_mark_processing_failed_does_not_overwrite_newer_generation() -> None:
    capture = _capture(generation=2)
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).mark_processing_failed(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_PENDING


def _proposal() -> ScenarioProposal:
    proposal = propose_capture_scenario(
        route="reminder", raw_text="明日の 9 時に起こして", now=NOW, timezone="Asia/Tokyo"
    )
    assert proposal is not None
    return proposal


async def _complete(
    repository: FakeProcessCaptureRepository,
    capture: Capture,
    *,
    processing_generation: int = 1,
    scenario: ScenarioProposal | None,
) -> Capture | None:
    return await repository.complete_capture_classification(
        capture_id=capture.id,
        processing_generation=processing_generation,
        category="reminder",
        route="reminder",
        urgency="normal",
        confidence=Decimal("0.9"),
        policy_version=CAPTURE_ROUTE_POLICY_VERSION,
        question_version=CAPTURE_QUESTION_VERSION,
        clarification_text=None,
        scenario=scenario,
    )


@pytest.mark.asyncio
async def test_complete_capture_stores_proposed_scenario_for_same_generation() -> None:
    capture = _capture(status=CAPTURE_STATUS_PROCESSING)
    repository = FakeProcessCaptureRepository(capture)
    proposal = _proposal()

    completed = await _complete(repository, capture, scenario=proposal)

    assert completed is not None
    scenario = repository.scenario
    assert scenario is not None
    assert scenario == proposal
    assert scenario.status == CAPTURE_SCENARIO_STATUS_PROPOSED
    assert scenario.policy_version == CAPTURE_SCENARIO_POLICY_VERSION


@pytest.mark.asyncio
async def test_complete_capture_does_not_store_scenario_for_other_generation() -> None:
    capture = _capture(status=CAPTURE_STATUS_PROCESSING)
    repository = FakeProcessCaptureRepository(capture)

    completed = await _complete(repository, capture, processing_generation=2, scenario=_proposal())

    assert completed is None
    assert repository.scenario is None
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_PROCESSING


@pytest.mark.asyncio
async def test_complete_capture_without_scenario_leaves_it_empty() -> None:
    capture = _capture(status=CAPTURE_STATUS_PROCESSING)
    repository = FakeProcessCaptureRepository(capture)

    completed = await _complete(repository, capture, scenario=None)

    assert completed is not None
    assert repository.scenario is None
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED


@pytest.mark.asyncio
async def test_process_capture_embeds_the_text_once_when_completed() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == ["牛乳を買う"]
    assert repository.embedding_lookups == [(capture.id, "牛乳を買う")]
    assert repository.embedding is not None
    assert repository.embedding.vector == (1, 0, 0, 0, 0, 0, 0, 0)
    assert repository.embedding.model == CAPTURE_EMBED_FAKE_MODEL
    assert repository.embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert repository.embedding.version == CAPTURE_EMBED_VERSION


@pytest.mark.asyncio
async def test_process_capture_does_not_embed_the_same_content_again() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, has_embedding=True)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == []
    assert repository.embedding is None
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED


@pytest.mark.asyncio
async def test_process_capture_does_not_embed_blank_text() -> None:
    capture = _capture(raw_text="   ")
    repository = FakeProcessCaptureRepository(capture)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == []
    assert repository.embedding_lookups == []
    assert repository.embedding is None


@pytest.mark.asyncio
async def test_reminder_saves_due_at_and_urgency_score() -> None:
    capture = _capture(raw_text="明日の 9 時に起こして")
    repository = FakeProcessCaptureRepository(capture)
    profiles = FakeProfileRepository("Asia/Tokyo")

    await _service(repository, profiles=profiles, clock=lambda: NOW).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.route == "reminder"
    assert profiles.lookups == [capture.user_id]
    assert repository.urgency_scores == [Decimal("0.50")]
    assert repository.scenario is not None
    assert repository.scenario.remind_text == "明日の 9 時"
    assert repository.scenario.due_at == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_non_reminder_does_not_read_the_user_timezone() -> None:
    capture = _capture(raw_text="牛乳を買う")
    repository = FakeProcessCaptureRepository(capture)
    profiles = FakeProfileRepository()

    await _service(repository, profiles=profiles, clock=lambda: NOW).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.route == "shopping"
    assert profiles.lookups == []
    assert repository.scenario is not None
    assert repository.scenario.due_at is None


@pytest.mark.asyncio
async def test_out_of_range_urgency_score_is_saved_as_null() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    classifier = ScriptedClassifier(
        Classification(
            category="shopping",
            confidence=Decimal("0.9"),
            urgency_score=1.5,
            question_version=CAPTURE_QUESTION_VERSION,
        )
    )

    await _service(repository, classifier).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.urgency_scores == [None]
