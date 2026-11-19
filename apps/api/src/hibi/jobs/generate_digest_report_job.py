from typing import Any
from uuid import UUID

from arq import Retry

from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.jobs.names import GENERATE_DIGEST_REPORT_JOB_NAME
from hibi.jobs.retry import retry_delay
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.service import DigestService
from hibi.modules.digests.types import (
    DIGEST_ERROR_GENERATION_FAILED,
    DIGEST_GENERATION_MAX_ATTEMPTS,
)


async def generate_digest_report_job(ctx: dict[str, Any], report_id: UUID) -> None:
    """ダイジェストまたは週次レビューの中身を 1 回作り、失敗したら指数バックオフで再試行させる。

    outbox の relay が、行を作ったあとに投入する。引数は `report_id` だけで、`user_id` や
    期間は、行から読む。arq は at-least-once で、同じ行に重複して届くことがあるが、
    `DigestService.generate_report` は `pending` の行だけを更新するので、先に別の job が
    `ready` か `failed` にした行は、書き換わらない。

    最終試行でも失敗したときは、行を `failed` にしてから例外を再送出する。`failed` への
    更新は、失敗した処理の session とは別の session で行う。元の session は例外で
    rollback されており、そのままでは書き込めないため。`error_code` には、失敗の種類を表す短い識別子
    (`DIGEST_ERROR_*`)だけを入れる。例外のクラス名やメッセージは入れない。
    内部の名前を契約にしないためと、メッセージが本文の断片を含み得るため。
    `failed` の行は、画面の「もう一度作る」で `pending` に戻り、新しい outbox から
    再実行される。

    Args:
        ctx: arq のジョブコンテキスト。`job_try` から現在の試行回数を読む。
        report_id: 中身を作る行の id。

    Raises:
        Retry: 最終試行より前に失敗した。待ち時間は指数バックオフで決める。
        Exception: 最終試行で失敗した。元の例外をそのまま送出する。
    """

    attempt = int(ctx["job_try"])

    # 通常はarqが実行前に止めるが、防御的に何もしない
    if attempt > DIGEST_GENERATION_MAX_ATTEMPTS:
        return

    try:
        async with session_scope() as session:
            service = DigestService(
                digests=DigestRepository(session=session),
                captures=CaptureRepository(session=session),
            )
            await service.generate_report(report_id)
    except Exception as error:
        is_final_attempt = attempt >= DIGEST_GENERATION_MAX_ATTEMPTS
        delay = None if is_final_attempt else retry_delay(attempt)

        if is_final_attempt:
            async with session_scope() as session:
                repository = DigestRepository(session=session)
                await repository.fail_report(report_id, error_code=_error_code(error))
        log_job_failure(
            job_name=GENERATE_DIGEST_REPORT_JOB_NAME,
            error=error,
            attempt=attempt,
            max_attempts=DIGEST_GENERATION_MAX_ATTEMPTS,
            context={
                "report_id": str(report_id),
                "retry_delay_seconds": delay,
            },
        )

        if delay is not None:
            raise Retry(defer=delay) from error

        raise


def _error_code(error: Exception) -> str:
    """失敗の種類を、画面と集計で使う短い識別子にする。

    例外のクラス名やメッセージは入れない。内部の名前を契約にしないためと、
    メッセージが本文の断片を含み得るため。
    """

    return DIGEST_ERROR_GENERATION_FAILED
