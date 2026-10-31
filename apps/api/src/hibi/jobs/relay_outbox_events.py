from typing import Any

from arq.connections import ArqRedis

from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_outbox_enqueue_failure
from hibi.jobs.process_capture_job import PROCESS_CAPTURE_JOB_NAME
from hibi.modules.captures.repository import CaptureRepository

_OUTBOX_BATCH_SIZE = 20


async def relay_outbox_events(ctx: dict[str, Any]) -> None:
    redis: ArqRedis = ctx["redis"]

    async with session_scope() as session:
        repository = CaptureRepository(session)

        events = await repository.list_pending_outbox_events(limit=_OUTBOX_BATCH_SIZE)

        for event in events:
            try:
                await redis.enqueue_job(
                    PROCESS_CAPTURE_JOB_NAME,
                    event.aggregate_id,
                    event.processing_generation,
                    _job_id=f"outbox:{event.id}",
                )
            except Exception as error:
                log_outbox_enqueue_failure(
                    error=error,
                    outbox_id=event.id,
                    aggregate_id=event.aggregate_id,
                    processing_generation=event.processing_generation,
                )
                continue

            await repository.update_outbox_published(outbox_id=event.id)
