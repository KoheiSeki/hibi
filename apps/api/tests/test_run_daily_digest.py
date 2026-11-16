from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module

import pytest

job_module = import_module("hibi.jobs.run_daily_digest")


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
async def test_run_daily_digest_commits_the_schedule_in_one_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = TransactionState()
    session = object()
    calls: list[str] = []

    class FakeService:
        def __init__(self, *, digests: object, captures: object) -> None:
            pass

        async def schedule_due_reports(self) -> int:
            calls.append("schedule")
            return 3

    monkeypatch.setattr(job_module, "session_scope", lambda: _session_scope(state, session))
    monkeypatch.setattr(job_module, "DigestRepository", lambda session: object())
    monkeypatch.setattr(job_module, "CaptureRepository", lambda session: object())
    monkeypatch.setattr(job_module, "DigestService", FakeService)

    await job_module.run_daily_digest({})

    assert calls == ["schedule"]
    assert state.committed is True
    assert state.rolled_back is False


@pytest.mark.asyncio
async def test_run_daily_digest_rolls_back_and_raises_when_the_schedule_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # cron は max_tries=1。次の 15 分後の実行が、足りない行を作り直す
    state = TransactionState()

    class FailingService:
        def __init__(self, *, digests: object, captures: object) -> None:
            pass

        async def schedule_due_reports(self) -> int:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(job_module, "session_scope", lambda: _session_scope(state, object()))
    monkeypatch.setattr(job_module, "DigestRepository", lambda session: object())
    monkeypatch.setattr(job_module, "CaptureRepository", lambda session: object())
    monkeypatch.setattr(job_module, "DigestService", FailingService)

    with pytest.raises(RuntimeError):
        await job_module.run_daily_digest({})

    assert state.committed is False
    assert state.rolled_back is True
