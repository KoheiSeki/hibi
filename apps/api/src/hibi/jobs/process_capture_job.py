import random
from typing import Any
from uuid import UUID

from arq import Retry

from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS
from hibi.modules.profiles.repository import ProfileRepository

PROCESS_CAPTURE_JOB_NAME = "process_capture_job"

_RETRY_BASE_DELAY_SECONDS = 5
_RETRY_JITTER_SECONDS = 1


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
        Retry: 最終試行より前に失敗した。待ち時間は _retry_delay で決める。
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
        retry_delay = None if is_final_attempt else _retry_delay(attempt)

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
                "retry_delay_seconds": retry_delay,
            },
        )

        if retry_delay is not None:
            raise Retry(defer=retry_delay) from error

        raise


def _retry_delay(attempt: int) -> float:
    """次の再試行までの待ち時間を、秒で返す。

    試行ごとに倍にする指数バックオフに、ジッターを足す。失敗したジョブが
    同時に再試行して、外部 API に負荷が集中するのを避けるため。

    Args:
        attempt: 失敗した試行の回数。1 始まり。

    Returns:
        待ち時間の秒数。
    """
    exponential_delay = _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return exponential_delay + random.uniform(0, _RETRY_JITTER_SECONDS)
