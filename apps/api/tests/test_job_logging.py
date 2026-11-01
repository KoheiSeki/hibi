from importlib import import_module
from typing import Any
from uuid import uuid7

import pytest

logging_module = import_module("hibi.jobs.job_logging")


class FakeLogger:
    def __init__(self) -> None:
        self.warning_calls: list[tuple[str, dict[str, Any]]] = []
        self.error_calls: list[tuple[str, dict[str, Any]]] = []

    def warning(self, event: str, **kwargs: Any) -> None:
        self.warning_calls.append((event, kwargs))

    def error(self, event: str, **kwargs: Any) -> None:
        self.error_calls.append((event, kwargs))


def test_log_job_failure_warns_when_retry_will_be_scheduled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(logging_module, "logger", logger)
    error = RuntimeError("temporary failure")

    logging_module.log_job_failure(
        job_name="process_capture_job",
        error=error,
        attempt=1,
        max_attempts=3,
        context={"capture_id": "capture-1", "retry_delay_seconds": 5.5},
    )

    assert logger.error_calls == []
    event, fields = logger.warning_calls[0]
    assert event == "job_attempt_failed"
    assert fields["final_attempt"] is False
    assert fields["retry_scheduled"] is True
    assert fields["attempt"] == 1
    assert fields["retry_delay_seconds"] == 5.5


def test_log_job_failure_errors_on_final_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(logging_module, "logger", logger)

    logging_module.log_job_failure(
        job_name="process_capture_job",
        error=RuntimeError("final failure"),
        attempt=3,
        max_attempts=3,
        context={"capture_id": "capture-1"},
    )

    assert logger.warning_calls == []
    event, fields = logger.error_calls[0]
    assert event == "job_attempt_failed"
    assert fields["final_attempt"] is True
    assert fields["retry_scheduled"] is False


def test_log_outbox_enqueue_failure_serializes_uuid_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    logger = FakeLogger()
    monkeypatch.setattr(logging_module, "logger", logger)
    outbox_id = uuid7()
    aggregate_id = uuid7()

    logging_module.log_outbox_enqueue_failure(
        error=ConnectionError("redis unavailable"),
        outbox_id=outbox_id,
        aggregate_id=aggregate_id,
        processing_generation=2,
    )

    event, fields = logger.error_calls[0]
    assert event == "outbox_enqueue_failed"
    assert fields["outbox_id"] == str(outbox_id)
    assert fields["aggregate_id"] == str(aggregate_id)
    assert fields["retry_on_next_relay"] is True
