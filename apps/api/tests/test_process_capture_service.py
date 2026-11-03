from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4, uuid7

import pytest

from hibi.ai.classification import (
    CAPTURE_QUESTION_VERSION,
    Classification,
    ClassificationTimeoutError,
)
from hibi.modules.captures.policies import CAPTURE_ROUTE_POLICY_VERSION
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    Capture,
)


class FakeProcessCaptureRepository:
    def __init__(
        self,
        capture: Capture | None,
        *,
        allow_start: bool = True,
        fail_processing: bool = False,
    ) -> None:
        self.capture = capture
        self.allow_start = allow_start
        self.fail_processing = fail_processing
        self.transitions: list[tuple[str, str]] = []
        self.classifications: list[dict[str, object]] = []

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
        )
        return self.capture


class RecordingClassifier:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def classify_capture(self, text: str, *, question_version: str) -> Classification:
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

    def classify_capture(self, text: str, *, question_version: str) -> Classification:
        del text, question_version
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


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
        created_at=now,
        updated_at=now,
    )


def _service(
    repository: FakeProcessCaptureRepository,
    classifier: RecordingClassifier | ScriptedClassifier | None = None,
) -> CaptureService:
    return CaptureService(object(), repository, classifier)  # type: ignore[arg-type]


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
    capture = _capture(raw_text="境界未満の牛乳")
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.category == "shopping"
    assert repository.capture.route == "clarify"
    assert repository.capture.confidence == Decimal("0.69")


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
