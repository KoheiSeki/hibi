from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any
from uuid import UUID, uuid7

import pytest

from hibi.jobs.names import RECOVER_STALLED_WORK_JOB_NAME

job_module = import_module("hibi.jobs.recover_stalled_work")

_NOW = datetime(2026, 11, 22, 0, 0, tzinfo=UTC)


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


class FakeLogger:
    def __init__(self) -> None:
        self.info_calls: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.info_calls.append((event, kwargs))


class FakeCaptureRepository:
    def __init__(self, recovered: int) -> None:
        self.recovered = recovered
        self.calls: list[dict[str, Any]] = []

    async def recover_stalled_captures(
        self, *, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]
    ) -> int:
        self.calls.append(
            {"stalled_before": stalled_before, "outbox_id_factory": outbox_id_factory}
        )
        return self.recovered


class FakeDigestRepository:
    def __init__(self, requeued: int) -> None:
        self.requeued = requeued
        self.calls: list[dict[str, Any]] = []

    async def requeue_stalled_reports(
        self, *, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]
    ) -> int:
        self.calls.append(
            {"stalled_before": stalled_before, "outbox_id_factory": outbox_id_factory}
        )
        return self.requeued


def _install(
    monkeypatch: pytest.MonkeyPatch,
    *,
    state: TransactionState,
    captures: object,
    digests: object,
) -> tuple[FakeLogger, list[object]]:
    session = object()
    sessions: list[object] = []
    logger = FakeLogger()

    def capture_repository(session: object) -> object:
        sessions.append(session)
        return captures

    def digest_repository(session: object) -> object:
        sessions.append(session)
        return digests

    monkeypatch.setattr(job_module, "session_scope", lambda: _session_scope(state, session))
    monkeypatch.setattr(job_module, "CaptureRepository", capture_repository)
    monkeypatch.setattr(job_module, "DigestRepository", digest_repository)
    monkeypatch.setattr(job_module, "utc_now", lambda: _NOW)
    monkeypatch.setattr(job_module, "logger", logger)
    return logger, sessions


def test_stalled_after_is_ten_minutes() -> None:
    assert timedelta(minutes=10) == job_module.STALLED_AFTER


@pytest.mark.asyncio
async def test_recover_stalled_work_calls_both_recoveries_with_the_cutoff_and_logs_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = TransactionState()
    captures = FakeCaptureRepository(recovered=2)
    digests = FakeDigestRepository(requeued=1)
    logger, sessions = _install(monkeypatch, state=state, captures=captures, digests=digests)

    await job_module.recover_stalled_work({})

    stalled_before = _NOW - timedelta(minutes=10)
    assert [call["stalled_before"] for call in captures.calls] == [stalled_before]
    assert [call["stalled_before"] for call in digests.calls] == [stalled_before]
    # outbox の id は、行ごとに新しく発行する
    assert captures.calls[0]["outbox_id_factory"] is uuid7
    assert digests.calls[0]["outbox_id_factory"] is uuid7
    # 2 つの回復は、1 つの session の 1 つの transaction で commit する
    assert len(sessions) == 2
    assert sessions[0] is sessions[1]
    assert state.committed is True
    # 件数だけを出し、本文やユーザーの内容は出さない
    assert logger.info_calls == [
        (
            "stalled_work_recovered",
            {
                "recovered_captures": 2,
                "requeued_digest_reports": 1,
                "stalled_before": stalled_before.isoformat(),
            },
        )
    ]


@pytest.mark.asyncio
async def test_recover_stalled_work_does_not_log_when_nothing_was_stalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 5 分ごとに動くので、何も無いときに毎回ログを出すと、ノイズになる
    state = TransactionState()
    logger, _ = _install(
        monkeypatch,
        state=state,
        captures=FakeCaptureRepository(recovered=0),
        digests=FakeDigestRepository(requeued=0),
    )

    await job_module.recover_stalled_work({})

    assert logger.info_calls == []
    assert state.committed is True


@pytest.mark.asyncio
async def test_recover_stalled_work_rolls_back_logs_and_raises_when_a_recovery_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # cron は max_tries=1。5 分後の次の実行が、同じ行をもう一度拾う
    state = TransactionState()
    failures: list[dict[str, Any]] = []

    class FailingDigestRepository:
        async def requeue_stalled_reports(
            self, *, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]
        ) -> int:
            raise RuntimeError("database unavailable")

    _install(
        monkeypatch,
        state=state,
        captures=FakeCaptureRepository(recovered=1),
        digests=FailingDigestRepository(),
    )
    monkeypatch.setattr(job_module, "log_job_failure", lambda **kwargs: failures.append(kwargs))

    with pytest.raises(RuntimeError):
        await job_module.recover_stalled_work({})

    assert state.committed is False
    assert state.rolled_back is True
    [failure] = failures
    assert failure["job_name"] == RECOVER_STALLED_WORK_JOB_NAME
    assert failure["attempt"] == 1
    assert failure["max_attempts"] == 1
