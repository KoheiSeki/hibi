"""arq に登録する job の名前。

relay やテストが、job の実装を import せずに、名前だけを参照できるように分けている。
名前は、`enqueue_job` に渡す文字列と、`WorkerSettings` の登録名を一致させる。
"""

PROCESS_CAPTURE_JOB_NAME = "process_capture_job"
GENERATE_DIGEST_REPORT_JOB_NAME = "generate_digest_report_job"
RUN_DAILY_DIGEST_JOB_NAME = "run_daily_digest"
