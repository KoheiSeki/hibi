from hibi.jobs.generate_digest_report_job import generate_digest_report_job
from hibi.jobs.main import WorkerSettings
from hibi.jobs.names import (
    GENERATE_DIGEST_REPORT_JOB_NAME,
    PROCESS_CAPTURE_JOB_NAME,
    RECOVER_STALLED_WORK_JOB_NAME,
)
from hibi.jobs.process_capture_job import process_capture_job
from hibi.jobs.recover_stalled_work import recover_stalled_work
from hibi.jobs.relay_outbox_events import relay_outbox_events
from hibi.jobs.run_daily_digest import run_daily_digest
from hibi.modules.captures.constants import (
    CAPTURE_PROCESSING_MAX_ATTEMPTS,
)


def _function(name: str):
    [function] = [function for function in WorkerSettings.functions if function.name == name]
    return function


def _cron_job(coroutine: object):
    [cron_job] = [cron for cron in WorkerSettings.cron_jobs if cron.coroutine is coroutine]
    return cron_job


def test_process_capture_job_registration() -> None:
    function = _function(PROCESS_CAPTURE_JOB_NAME)

    assert function.coroutine is process_capture_job
    assert function.max_tries == CAPTURE_PROCESSING_MAX_ATTEMPTS


def test_outbox_relay_cron_runs_every_five_seconds() -> None:
    cron_job = _cron_job(relay_outbox_events)

    assert cron_job.second == set(range(0, 60, 5))
    assert cron_job.microsecond == 0
    assert cron_job.run_at_startup is True
    assert cron_job.unique is True
    assert cron_job.max_tries == 1


def test_worker_registers_the_digest_job_and_the_daily_digest_cron() -> None:
    function = _function(GENERATE_DIGEST_REPORT_JOB_NAME)
    cron_job = _cron_job(run_daily_digest)

    assert function.coroutine is generate_digest_report_job
    assert function.max_tries == 3
    # 15 分ごとの、00 秒に 1 回。複数の worker が回しても、1 つだけが走る
    assert cron_job.minute == {0, 15, 30, 45}
    assert cron_job.second == 0
    assert cron_job.unique is True
    assert cron_job.max_tries == 1


def test_worker_registers_the_stalled_work_recovery_cron() -> None:
    cron_job = _cron_job(recover_stalled_work)

    assert cron_job.name == RECOVER_STALLED_WORK_JOB_NAME
    # 5 分ごとの、00 秒に 1 回。複数の worker が回しても、1 つだけが走る
    assert cron_job.minute == set(range(0, 60, 5))
    assert cron_job.second == 0
    assert cron_job.unique is True
    assert cron_job.max_tries == 1
