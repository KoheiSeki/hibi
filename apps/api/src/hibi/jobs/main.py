from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.worker import Function, func

from hibi.core.config import get_settings
from hibi.jobs.generate_digest_report_job import generate_digest_report_job
from hibi.jobs.names import (
    GENERATE_DIGEST_REPORT_JOB_NAME,
    PROCESS_CAPTURE_JOB_NAME,
    RUN_DAILY_DIGEST_JOB_NAME,
)
from hibi.jobs.process_capture_job import process_capture_job
from hibi.jobs.relay_outbox_events import relay_outbox_events
from hibi.jobs.run_daily_digest import run_daily_digest
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS
from hibi.modules.digests.types import DIGEST_GENERATION_MAX_ATTEMPTS


class WorkerSettings:
    functions: ClassVar[list[Function]] = [
        func(
            process_capture_job,
            name=PROCESS_CAPTURE_JOB_NAME,
            max_tries=CAPTURE_PROCESSING_MAX_ATTEMPTS,
        ),
        func(
            generate_digest_report_job,
            name=GENERATE_DIGEST_REPORT_JOB_NAME,
            max_tries=DIGEST_GENERATION_MAX_ATTEMPTS,
        ),
    ]

    cron_jobs: ClassVar[list[CronJob]] = [
        cron(
            relay_outbox_events,
            second=set(range(0, 60, 5)),
            microsecond=0,
            run_at_startup=True,
            unique=True,
            max_tries=1,
        ),
        cron(
            run_daily_digest,
            name=RUN_DAILY_DIGEST_JOB_NAME,
            minute={0, 15, 30, 45},
            second=0,
            unique=True,
            max_tries=1,
        ),
    ]

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
