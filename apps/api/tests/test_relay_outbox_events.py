from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any
from uuid import UUID, uuid7

import pytest

from hibi.jobs.process_capture_job import PROCESS_CAPTURE_JOB_NAME
from hibi.modules.captures.types import OutboxEvent

relay_module = import_module("hibi.jobs.relay_outbox_events")


@asynccontextmanager
async def _session_scope() -> AsyncGenerator[object]:
    yield object()


class FakeOutboxRepository:
    def __init__(self, events: list[OutboxEvent]) -> None:
        self.events = events
        self.requested_limit: int | None = None
        self.published_ids: list[UUID] = []

    async def list_pending_outbox_events(self, *, limit: int) -> list[OutboxEvent]:
        self.requested_limit = limit
        return self.events

    async def update_outbox_published(self, *, outbox_id: UUID) -> bool:
        self.published_ids.append(outbox_id)
        return True


class FakeRedis:
    def __init__(self, outcomes: dict[UUID, object | Exception | None]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> object | None:
        self.calls.append((function, args, kwargs))
        aggregate_id = args[0]
        outcome = self.outcomes[aggregate_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _event(*, generation: int = 1) -> OutboxEvent:
    return OutboxEvent(
        id=uuid7(),
        aggregate_id=uuid7(),
        processing_generation=generation,
    )


def _patch_repository(monkeypatch: pytest.MonkeyPatch, repository: FakeOutboxRepository) -> None:
    monkeypatch.setattr(relay_module, "session_scope", _session_scope)
    monkeypatch.setattr(relay_module, "CaptureRepository", lambda _session: repository)


@pytest.mark.asyncio
async def test_relay_publishes_new_and_already_enqueued_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_event = _event()
    existing_event = _event(generation=2)
    repository = FakeOutboxRepository([new_event, existing_event])
    redis = FakeRedis(
        {
            new_event.aggregate_id: object(),
            existing_event.aggregate_id: None,
        }
    )
    _patch_repository(monkeypatch, repository)

    await relay_module.relay_outbox_events({"redis": redis})

    assert repository.requested_limit == 20
    assert repository.published_ids == [new_event.id, existing_event.id]
    assert redis.calls == [
        (
            PROCESS_CAPTURE_JOB_NAME,
            (new_event.aggregate_id, new_event.processing_generation),
            {"_job_id": f"outbox:{new_event.id}"},
        ),
        (
            PROCESS_CAPTURE_JOB_NAME,
            (existing_event.aggregate_id, existing_event.processing_generation),
            {"_job_id": f"outbox:{existing_event.id}"},
        ),
    ]


@pytest.mark.asyncio
async def test_relay_keeps_failed_event_pending_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_event = _event()
    successful_event = _event()
    repository = FakeOutboxRepository([failed_event, successful_event])
    redis = FakeRedis(
        {
            failed_event.aggregate_id: ConnectionError("redis unavailable"),
            successful_event.aggregate_id: object(),
        }
    )
    logged: list[dict[str, Any]] = []
    _patch_repository(monkeypatch, repository)
    monkeypatch.setattr(
        relay_module,
        "log_outbox_enqueue_failure",
        lambda **kwargs: logged.append(kwargs),
    )

    await relay_module.relay_outbox_events({"redis": redis})

    assert repository.published_ids == [successful_event.id]
    assert logged[0]["outbox_id"] == failed_event.id
    assert logged[0]["aggregate_id"] == failed_event.aggregate_id
    assert logged[0]["processing_generation"] == failed_event.processing_generation
