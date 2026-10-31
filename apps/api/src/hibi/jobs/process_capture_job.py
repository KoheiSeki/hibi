from typing import Any
from uuid import UUID

from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS


async def process_capture_job(
    ctx: dict[str, Any], capture_id: UUID, processing_generation: int
) -> None:
    attempt = int(ctx["job_try"])

    try:
        async with session_scope() as session:
            service = CaptureService(session=session, repository=CaptureRepository(session=session))
            await service.process_capture(capture_id, processing_generation)
    except Exception as error:
        if attempt >= CAPTURE_PROCESSING_MAX_ATTEMPTS:
            async with session_scope() as session:
                service = CaptureService(
                    session=session, repository=CaptureRepository(session=session)
                )
                await service.mark_processing_failed(capture_id, processing_generation)
        log_job_failure(
            job_name="process_capture_job",
            error=error,
            attempt=attempt,
            max_attempts=CAPTURE_PROCESSING_MAX_ATTEMPTS,
            context={
                "capture_id": str(capture_id),
                "processing_generation": processing_generation,
            },
        )
        raise
