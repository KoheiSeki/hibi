from typing import Any

from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.jobs.names import RUN_DAILY_DIGEST_JOB_NAME
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.service import DigestService

_MAX_ATTEMPTS = 1


async def run_daily_digest(ctx: dict[str, Any]) -> None:
    """今が作る時刻の利用者に、ダイジェストと週次レビューの行を作り、生成を予約する。

    arq の cron が 15 分ごとに呼ぶ。ユーザーごとの予定は持たず、実行のたびに、
    作る時刻になっていて、行がまだ無い利用者を探す。名前は daily だが、同じ実行で
    月曜の週次レビューも予約する。中身はここでは作らない。outbox を経由して、
    `generate_digest_report_job` が作る。

    行の作成と outbox の追加は、1 つの session の 1 つの transaction で commit する。
    途中で失敗したら、すべて rollback して例外を上げる。cron は `max_tries=1` で再試行
    しないが、15 分後の次の実行が、足りない行を作り直す。同じ期間の行は、既にあれば
    何もしないので、再実行しても二重に作られない。`unique=True` により、複数の worker が
    あっても、同じ時刻に走るのは 1 つだけ。

    Args:
        ctx: arq のジョブコンテキスト。使わない。cron の関数の形に合わせるための引数。

    Raises:
        Exception: 利用者の読み出しや、行の作成に失敗した。transaction は rollback 済み。
    """

    try:
        async with session_scope() as session:
            service = DigestService(
                digests=DigestRepository(session=session),
                captures=CaptureRepository(session=session),
            )
            await service.schedule_due_reports()
    except Exception as error:
        log_job_failure(
            job_name=RUN_DAILY_DIGEST_JOB_NAME,
            error=error,
            attempt=_MAX_ATTEMPTS,
            max_attempts=_MAX_ATTEMPTS,
            context={},
        )
        raise
