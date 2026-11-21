from typing import Any
from uuid import UUID

from arq import Retry

from hibi.ai.factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.jobs.names import PROCESS_CAPTURE_JOB_NAME
from hibi.jobs.retry import retry_delay
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS
from hibi.modules.profiles.repository import ProfileRepository


async def process_capture_job(
    ctx: dict[str, Any], capture_id: UUID, processing_generation: int
) -> None:
    """Capture の AI 処理を 1 回実行し、失敗したら指数バックオフで再試行させる。

    最終試行でも失敗したときは、Capture を failed にしてから例外を再送出する。
    failed への更新は、失敗した処理のセッションとは別のセッションで行う。
    元のセッションは例外で rollback されており、そのままでは書き込めないため。

    Args:
        ctx: arq のジョブコンテキスト。job_try から現在の試行回数を読む。
        capture_id: 処理する Capture。
        processing_generation: ジョブが想定する処理の世代。

    Raises:
        Retry: 最終試行より前に失敗した。待ち時間は `retry_delay` で決める。
        Exception: 最終試行で失敗した。元の例外をそのまま送出する。
    """
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
                generator=build_clarification_generator(),
                embedder=build_text_embedder(),
                profiles=ProfileRepository(session=session),
            )
            await service.process_capture(capture_id, processing_generation)
    except Exception as error:
        is_final_attempt = attempt >= CAPTURE_PROCESSING_MAX_ATTEMPTS
        delay = None if is_final_attempt else retry_delay(attempt)

        if is_final_attempt:
            async with session_scope() as session:
                service = CaptureService(
                    session=session,
                    repository=CaptureRepository(session=session),
                    classifier=build_capture_classifier(),
                    generator=build_clarification_generator(),
                    embedder=build_text_embedder(),
                    profiles=ProfileRepository(session=session),
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
                "retry_delay_seconds": delay,
            },
        )

        if delay is not None:
            raise Retry(defer=delay) from error

        raise
