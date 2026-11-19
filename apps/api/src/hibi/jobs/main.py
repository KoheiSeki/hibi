from typing import ClassVar

from arq import cron
from arq.connections import RedisSettings
from arq.cron import CronJob
from arq.worker import Function, func

from hibi.core.config import get_settings
from hibi.jobs.names import PROCESS_CAPTURE_JOB_NAME
from hibi.jobs.process_capture_job import process_capture_job
from hibi.jobs.relay_outbox_events import relay_outbox_events
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS


class WorkerSettings:
    functions: ClassVar[list[Function]] = [
        func(
            process_capture_job,
            name=PROCESS_CAPTURE_JOB_NAME,
            max_tries=CAPTURE_PROCESSING_MAX_ATTEMPTS,
        )
    ]

    cron_jobs: ClassVar[list[CronJob]] = [
        cron(
            relay_outbox_events,
            second=set(range(0, 60, 5)),
            microsecond=0,
            run_at_startup=True,
            unique=True,
            max_tries=1,
        )
    ]

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
