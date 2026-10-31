from typing import Any

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
