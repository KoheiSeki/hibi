from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any
from uuid import UUID, uuid7

import pytest

job_module = import_module("hibi.jobs.process_capture_job")


class TransactionState:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False


@asynccontextmanager
async def _session_scope(state: TransactionState, session: object) -> AsyncGenerator[object]:
    try:
        yield session
        state.committed = True
    except Exception:
        state.rolled_back = True
        raise


@pytest.mark.asyncio
async def test_process_capture_job_commits_successful_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = TransactionState()
    session = object()
    calls: list[tuple[UUID, int]] = []

    class FakeService:
        def __init__(self, *, session: object, repository: object) -> None:
            pass

        async def process_capture(self, capture_id: UUID, processing_generation: int) -> None:
            calls.append((capture_id, processing_generation))

    monkeypatch.setattr(job_module, "session_scope", lambda: _session_scope(state, session))
    monkeypatch.setattr(job_module, "CaptureRepository", lambda *, session: object())
    monkeypatch.setattr(job_module, "CaptureService", FakeService)
    capture_id = uuid7()

    await job_module.process_capture_job({"job_try": 2}, capture_id, processing_generation=3)

    assert calls == [(capture_id, 3)]
    assert state.committed is True
    assert state.rolled_back is False


@pytest.mark.asyncio
async def test_process_capture_job_rolls_back_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = TransactionState()
    session = object()

    class FailingService:
        def __init__(self, *, session: object, repository: object) -> None:
            pass

        async def process_capture(self, capture_id: UUID, processing_generation: int) -> None:
            raise RuntimeError("processing failed")

    monkeypatch.setattr(job_module, "session_scope", lambda: _session_scope(state, session))
    monkeypatch.setattr(job_module, "CaptureRepository", lambda *, session: object())
    monkeypatch.setattr(job_module, "CaptureService", FailingService)
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(job_module, "log_job_failure", lambda **kwargs: logged.append(kwargs))

    with pytest.raises(RuntimeError, match="processing failed"):
        await job_module.process_capture_job({"job_try": 1}, uuid7(), processing_generation=1)

    assert state.committed is False
    assert state.rolled_back is True
    assert logged[0]["attempt"] == 1


@pytest.mark.asyncio
async def test_process_capture_job_commits_failed_status_in_separate_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    processing_state = TransactionState()
    failure_state = TransactionState()
    processing_session = object()
    failure_session = object()
    scopes = iter(
        [
            _session_scope(processing_state, processing_session),
            _session_scope(failure_state, failure_session),
        ]
    )
    marked_failed: list[tuple[UUID, int]] = []

    class FailingService:
        def __init__(self, *, session: object, repository: object) -> None:
            self._session = session

        async def process_capture(self, capture_id: UUID, processing_generation: int) -> None:
            raise RuntimeError("processing failed")

        async def mark_processing_failed(
            self, capture_id: UUID, processing_generation: int
        ) -> None:
            assert self._session is failure_session
            marked_failed.append((capture_id, processing_generation))

    monkeypatch.setattr(job_module, "session_scope", lambda: next(scopes))
    monkeypatch.setattr(job_module, "CaptureRepository", lambda *, session: object())
    monkeypatch.setattr(job_module, "CaptureService", FailingService)
    monkeypatch.setattr(job_module, "log_job_failure", lambda **kwargs: None)
    capture_id = uuid7()

    with pytest.raises(RuntimeError, match="processing failed"):
        await job_module.process_capture_job({"job_try": 3}, capture_id, processing_generation=2)

    assert processing_state.rolled_back is True
    assert processing_state.committed is False
    assert failure_state.committed is True
    assert failure_state.rolled_back is False
    assert marked_failed == [(capture_id, 2)]
