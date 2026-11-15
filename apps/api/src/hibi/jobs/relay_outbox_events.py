from typing import Any

from arq.connections import ArqRedis

from hibi.db.session import session_scope
from hibi.jobs.generate_digest_report_job import GENERATE_DIGEST_REPORT_JOB_NAME
from hibi.jobs.job_logging import log_outbox_enqueue_failure
from hibi.jobs.process_capture_job import PROCESS_CAPTURE_JOB_NAME
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.types import OutboxEvent
from hibi.modules.digests.types import DIGEST_AGGREGATE_TYPE

_OUTBOX_BATCH_SIZE = 20


async def relay_outbox_events(ctx: dict[str, Any]) -> None:
    redis: ArqRedis = ctx["redis"]

    async with session_scope() as session:
        repository = CaptureRepository(session)

        events = await repository.list_pending_outbox_events(limit=_OUTBOX_BATCH_SIZE)

        for event in events:
            job_name, job_args = _job_for(event)
            try:
                await redis.enqueue_job(job_name, *job_args, _job_id=f"outbox:{event.id}")
            except Exception as error:
                log_outbox_enqueue_failure(
                    error=error,
                    target_job=job_name,
                    outbox_id=event.id,
                    aggregate_id=event.aggregate_id,
                    processing_generation=event.processing_generation,
                )
                continue

            await repository.update_outbox_published(outbox_id=event.id)


def _job_for(event: OutboxEvent) -> tuple[str, tuple[Any, ...]]:
    """outbox の種類から、投入する job の名前と引数を決める。

    digest は再実行しても同じ結果になる job なので、世代を持たず、id だけを渡す。
    capture は古い世代の job を無視するために、処理の世代も渡す。
    """

    if event.aggregate_type == DIGEST_AGGREGATE_TYPE:
        return GENERATE_DIGEST_REPORT_JOB_NAME, (event.aggregate_id,)
    return PROCESS_CAPTURE_JOB_NAME, (event.aggregate_id, event.processing_generation)
