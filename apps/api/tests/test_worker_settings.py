from hibi.jobs.main import WorkerSettings
from hibi.jobs.process_capture_job import (
    PROCESS_CAPTURE_JOB_NAME,
    process_capture_job,
)
from hibi.jobs.relay_outbox_events import relay_outbox_events
from hibi.modules.captures.types import CAPTURE_PROCESSING_MAX_ATTEMPTS


def test_process_capture_job_registration() -> None:
    [function] = WorkerSettings.functions

    assert function.name == PROCESS_CAPTURE_JOB_NAME
    assert function.coroutine is process_capture_job
    assert function.max_tries == CAPTURE_PROCESSING_MAX_ATTEMPTS


def test_outbox_relay_cron_runs_every_five_seconds() -> None:
    [cron_job] = WorkerSettings.cron_jobs

    assert cron_job.coroutine is relay_outbox_events
    assert cron_job.second == set(range(0, 60, 5))
    assert cron_job.microsecond == 0
    assert cron_job.run_at_startup is True
    assert cron_job.unique is True
    assert cron_job.max_tries == 1
