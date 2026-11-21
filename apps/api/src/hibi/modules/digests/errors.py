from uuid import UUID

from hibi.core.errors import ApplicationError


class DigestReportNotFoundError(ApplicationError):
    """行が無い、または別ユーザーの行。

    他人の行の存在を明かさないため、どちらも同じ 404 にする。
    """

    problem_type = "digest-report-not-found"
    title = "Digest report not found"
    status = 404
    detail = "The requested digest report does not exist."

    def __init__(self, report_id: UUID) -> None:
        self.report_id = report_id
        super().__init__()


class DigestReportNotRetryableError(ApplicationError):
    """retry できるのは failed の行だけで、pending と ready は 409 にする。"""

    problem_type = "digest-report-not-retryable"
    title = "Digest report cannot be retried"
    status = 409
    detail = "Only failed digest reports can be retried."
