from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


def log_job_failure(
    *, job_name: str, error: Exception, attempt: int, max_attempts: int, context: dict[str, Any]
) -> None:
    logger.error(
        "job failed",
        job_name=job_name,
        attempt=attempt,
        max_attempts=max_attempts,
        final_attempt=attempt >= max_attempts,
        error_type=type(error).__name__,
        **context,
        exc_info=(type(error), error, error.__traceback__),
    )


def log_outbox_enqueue_failure(
    *, error, outbox_id: UUID, aggregate_id: UUID, processing_generation: int
) -> None:
    logger.error(
        "outbox_enqueue_failed",
        relay_job="relay_outbox_events",
        target_job="process_capture_job",
        outbox_id=outbox_id,
        aggregate_id=aggregate_id,
        processing_generation=processing_generation,
        retry_on_next_relay=True,
        error_type=type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )
