from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid7

import pytest

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
        if status == CAPTURE_STATUS_COMPLETED and self.fail_processing:
            raise RuntimeError("temporary processing failure")
        if (
            self.capture is None
            or self.capture.id != capture_id
            or self.capture.processing_generation != processing_generation
            or self.capture.status != expected_status
        ):
            return False
        self.capture = replace(self.capture, status=status)
        return True


def _capture(*, status: str = CAPTURE_STATUS_PENDING, generation: int = 1) -> Capture:
    now = datetime.now(UTC)
    return Capture(
        id=uuid7(),
        user_id=uuid4(),
        raw_text="牛乳を買う",
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
) -> CaptureService:
    return CaptureService(object(), repository)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_process_capture_transitions_pending_to_completed() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)

    await _service(repository).process_capture(capture.id, 1)

    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED
    assert repository.transitions == [
        (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_PROCESSING),
        (CAPTURE_STATUS_PROCESSING, CAPTURE_STATUS_COMPLETED),
    ]


@pytest.mark.asyncio
async def test_process_capture_stops_when_pending_claim_fails() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, allow_start=False)

    await _service(repository).process_capture(capture.id, 1)

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
    capture_id = capture.id if capture is not None else uuid7()

    await _service(repository).process_capture(capture_id, processing_generation)

    assert repository.transitions == []


@pytest.mark.asyncio
async def test_process_capture_reraises_processing_failure() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, fail_processing=True)

    with pytest.raises(RuntimeError, match="temporary processing failure"):
        await _service(repository).process_capture(capture.id, 1)

    assert repository.transitions == [
        (CAPTURE_STATUS_PENDING, CAPTURE_STATUS_PROCESSING),
        (CAPTURE_STATUS_PROCESSING, CAPTURE_STATUS_COMPLETED),
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
