from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any
from uuid import UUID, uuid7

import pytest
from arq import Retry

job_module = import_module("hibi.jobs.generate_digest_report_job")

# spec: 3 回目の失敗で failed にする
_FINAL_ATTEMPT = 3


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


class FakeDigestRepository:
    """`fail_report` が、どの session で呼ばれたかを記録する fake。"""

    failed: list[tuple[object, UUID, str]] = []  # noqa: RUF012

    def __init__(self, session: object) -> None:
        self._session = session

    async def fail_report(self, report_id: UUID, *, error_code: str) -> bool:
        self.failed.append((self._session, report_id, error_code))
        return True


@pytest.fixture(autouse=True)
def _reset_failed() -> None:
    FakeDigestRepository.failed = []


def _patch_job(
    monkeypatch: pytest.MonkeyPatch, service: type, scopes: list[Any]
) -> list[dict[str, Any]]:
    iterator = iter(scopes)
    logged: list[dict[str, Any]] = []
    monkeypatch.setattr(job_module, "session_scope", lambda: next(iterator))
    monkeypatch.setattr(job_module, "DigestRepository", FakeDigestRepository)
    monkeypatch.setattr(job_module, "CaptureRepository", lambda session: object())
    monkeypatch.setattr(job_module, "DigestService", service)
    monkeypatch.setattr(job_module, "log_job_failure", lambda **kwargs: logged.append(kwargs))
    return logged


@pytest.mark.asyncio
async def test_job_commits_a_successful_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    state = TransactionState()
    generated: list[UUID] = []

    class FakeService:
        def __init__(self, *, digests: object, captures: object, summarizer: object) -> None:
            pass

        async def generate_report(self, report_id: UUID) -> None:
            generated.append(report_id)

    _patch_job(monkeypatch, FakeService, [_session_scope(state, object())])
    report_id = uuid7()

    await job_module.generate_digest_report_job({"job_try": 2}, report_id)

    assert generated == [report_id]
    assert state.committed is True
    assert state.rolled_back is False
    assert FakeDigestRepository.failed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("attempt", [1, 2])
async def test_job_schedules_a_retry_before_the_final_attempt(
    monkeypatch: pytest.MonkeyPatch, attempt: int
) -> None:
    state = TransactionState()

    class FailingService:
        def __init__(self, *, digests: object, captures: object, summarizer: object) -> None:
            pass

        async def generate_report(self, report_id: UUID) -> None:
            raise RuntimeError("generation failed")

    logged = _patch_job(monkeypatch, FailingService, [_session_scope(state, object())])

    with pytest.raises(Retry) as retry:
        await job_module.generate_digest_report_job({"job_try": attempt}, uuid7())

    assert state.committed is False
    assert state.rolled_back is True
    assert retry.value.defer_score is not None
    assert retry.value.defer_score > 0
    assert isinstance(retry.value.__cause__, RuntimeError)
    assert logged[0]["attempt"] == attempt
    # 最終試行より前は、failed にしない。次の試行で成功するかもしれない
    assert FakeDigestRepository.failed == []


@pytest.mark.asyncio
async def test_job_marks_failed_on_the_final_attempt_in_a_separate_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_state = TransactionState()
    failure_state = TransactionState()
    generation_session = object()
    failure_session = object()

    class FailingService:
        def __init__(self, *, digests: object, captures: object, summarizer: object) -> None:
            pass

        async def generate_report(self, report_id: UUID) -> None:
            raise RuntimeError("raw title: 牛乳を買う")

    logged = _patch_job(
        monkeypatch,
        FailingService,
        [
            _session_scope(generation_state, generation_session),
            _session_scope(failure_state, failure_session),
        ],
    )
    report_id = uuid7()

    with pytest.raises(RuntimeError):
        await job_module.generate_digest_report_job({"job_try": _FINAL_ATTEMPT}, report_id)

    # 失敗した処理の session は rollback 済みなので、failed への更新は別の session で行う
    assert generation_state.rolled_back is True
    assert failure_state.committed is True
    [(session, failed_id, error_code)] = FakeDigestRepository.failed
    assert session is failure_session
    assert failed_id == report_id
    # error_code は理由の種類だけ。例外のメッセージ(本文の断片を含み得る)は入れない
    assert error_code
    assert "牛乳" not in error_code
    assert logged[0]["attempt"] == _FINAL_ATTEMPT


@pytest.mark.asyncio
async def test_job_does_nothing_after_the_final_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    # 通常は arq が実行前に止める。防御的に、何も変えない
    class UnexpectedService:
        def __init__(self, *, digests: object, captures: object, summarizer: object) -> None:
            raise AssertionError("the service must not be built")

    _patch_job(monkeypatch, UnexpectedService, [])

    await job_module.generate_digest_report_job({"job_try": _FINAL_ATTEMPT + 1}, uuid7())

    assert FakeDigestRepository.failed == []
