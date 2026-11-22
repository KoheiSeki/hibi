from datetime import timedelta
from typing import Any
from uuid import uuid7

import structlog

from hibi.core.timezone import utc_now
from hibi.db.session import session_scope
from hibi.jobs.job_logging import log_job_failure
from hibi.jobs.names import RECOVER_STALLED_WORK_JOB_NAME
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.repository import DigestRepository

STALLED_AFTER = timedelta(minutes=10)
_MAX_ATTEMPTS = 1

logger = structlog.get_logger(__name__)


async def recover_stalled_work(ctx: dict[str, Any]) -> None:
    """止まった Capture の処理と、止まった digest の生成を、もう一度予約する。

    arq の cron が 5 分ごとに呼ぶ。worker が job の途中で落ちたり、job が失われたり
    すると、Capture は processing のまま、digest は pending のまま残り、誰も進めない。
    `updated_at` が `STALLED_AFTER`(10 分)より前のまま変わっていない行を、止まったと
    見なす。10 分は、ふつうの job が終わるまでの時間より十分に長い。それでも、遅れて
    動いていた job を止まったと見なすことはあるが、Capture は世代、digest は pending
    だけを進める更新が、二重の書き込みを防ぐ。

    2 つの回復は、1 つの session の 1 つの transaction で commit する。どちらも
    条件つきの 1 回の更新なので、何度実行しても、同じ行に outbox を重ねない。
    `unique=True` により、複数の worker があっても、同じ時刻に走るのは 1 つだけ。

    回復した件数は、1 件以上あったときだけ `stalled_work_recovered` のログに出す。
    5 分ごとに動くので、0 件のログはノイズになる。出すのは件数と基準の時刻だけで、
    本文やユーザーの内容は出さない。

    途中で失敗したら、すべて rollback し、失敗をログに出して例外を上げる。cron は
    `max_tries=1` で再試行しないが、5 分後の次の実行が、同じ行をもう一度拾う。

    Args:
        ctx: arq のジョブコンテキスト。使わない。cron の関数の形に合わせるための引数。

    Raises:
        Exception: 回復の読み出しや更新に失敗した。transaction は rollback 済み。
    """

    stalled_before = utc_now() - STALLED_AFTER

    try:
        async with session_scope() as session:
            recovered = await CaptureRepository(session=session).recover_stalled_captures(
                stalled_before=stalled_before, outbox_id_factory=uuid7
            )
            requeued = await DigestRepository(session=session).requeue_stalled_reports(
                stalled_before=stalled_before, outbox_id_factory=uuid7
            )
    except Exception as error:
        log_job_failure(
            job_name=RECOVER_STALLED_WORK_JOB_NAME,
            error=error,
            attempt=_MAX_ATTEMPTS,
            max_attempts=_MAX_ATTEMPTS,
            context={},
        )
        raise

    if recovered or requeued:
        logger.info(
            "stalled_work_recovered",
            recovered_captures=recovered,
            requeued_digest_reports=requeued,
            stalled_before=stalled_before.isoformat(),
        )
