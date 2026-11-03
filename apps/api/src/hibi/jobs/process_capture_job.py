import random
from typing import Any
from uuid import UUID

from arq import Retry

from hibi.ai.classifier_factory import build_capture_classifier
from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS

PROCESS_CAPTURE_JOB_NAME = "process_capture_job"

_RETRY_BASE_DELAY_SECONDS = 5
_RETRY_JITTER_SECONDS = 1


async def process_capture_job(
    ctx: dict[str, Any], capture_id: UUID, processing_generation: int
) -> None:
    attempt = int(ctx["job_try"])

    # 通常はarqが実行前に止めるが、防御的に何もしない
    if attempt > CAPTURE_PROCESSING_MAX_ATTEMPTS:
        return

    try:
        async with session_scope() as session:
            service = CaptureService(
                session=session,
                repository=CaptureRepository(session=session),
                classifier=build_capture_classifier(),
            )
            await service.process_capture(capture_id, processing_generation)
    except Exception as error:
        is_final_attempt = attempt >= CAPTURE_PROCESSING_MAX_ATTEMPTS
        retry_delay = None if is_final_attempt else _retry_delay(attempt)

        if is_final_attempt:
            async with session_scope() as session:
                service = CaptureService(
                    session=session,
                    repository=CaptureRepository(session=session),
                    classifier=build_capture_classifier(),
                )
                await service.mark_processing_failed(capture_id, processing_generation)
        log_job_failure(
            job_name=PROCESS_CAPTURE_JOB_NAME,
            error=error,
            attempt=attempt,
            max_attempts=CAPTURE_PROCESSING_MAX_ATTEMPTS,
            context={
                "capture_id": str(capture_id),
                "processing_generation": processing_generation,
                "retry_delay_seconds": retry_delay,
            },
        )

        if retry_delay is not None:
            raise Retry(defer=retry_delay) from error

        raise


def _retry_delay(attempt: int) -> float:
    exponential_delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return exponential_delay + random.uniform(0, _RETRY_JITTER_SECONDS)
