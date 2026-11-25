"""ダイジェストの service と job のテストが共有する fake と、値を作る補助。"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from hibi.ai.review_summary import WeeklyReviewInput
from hibi.modules.captures.constants import (
    CAPTURE_STATUS_COMPLETED,
)
from hibi.modules.captures.today import TodayCandidate
from hibi.modules.captures.types import (
    Capture,
    CaptureScenario,
)
from hibi.modules.digests.constants import (
    DIGEST_KIND_DAILY,
    DIGEST_STATUS_PENDING,
)
from hibi.modules.digests.types import (
    ActiveUser,
    DigestReport,
)

TOKYO_USER = ActiveUser(user_id=UUID(int=10), timezone="Asia/Tokyo")
NEW_YORK_USER = ActiveUser(user_id=UUID(int=11), timezone="America/New_York")

CREATED = datetime(2026, 11, 1, tzinfo=UTC)
# 2026-11-10 15:00 JST。Today のテストと同じ時刻と期限を使う
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
OVERDUE = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)  # 09:00 JST
LATER_TODAY = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)  # 20:00 JST

NO_DEADLINE_ID = UUID(int=1)
OVERDUE_ID = UUID(int=2)
TODAY_ID = UUID(int=3)

ClaimKey = tuple[UUID, str, date]


class FakeDigestRepository:
    """`DigestRepository` の代わりに、呼び出しを記録する fake。"""

    def __init__(
        self,
        *,
        users: Sequence[ActiveUser] = (),
        report: DigestReport | None = None,
        existing: frozenset[ClaimKey] = frozenset(),
        done_count: int = 0,
        captured_count: int = 0,
        done_titles: Sequence[str] = (),
        listed: Sequence[DigestReport] = (),
        requeued: DigestReport | None = None,
    ) -> None:
        self.users = list(users)
        self.report = report
        self.existing = existing
        self.done_count = done_count
        self.captured_count = captured_count
        self.done_titles = list(done_titles)
        self.listed = list(listed)
        self.requeued = requeued
        self.list_calls: list[dict[str, object]] = []
        self.requeue_calls: list[dict[str, object]] = []
        self.active_user_calls: list[dict[str, object]] = []
        self.claims: list[dict[str, object]] = []
        self.completed: list[tuple[UUID, dict[str, object], str | None]] = []
        self.failed: list[tuple[UUID, str]] = []
        self.done_calls: list[tuple[UUID, datetime, datetime]] = []
        self.captured_calls: list[tuple[UUID, datetime, datetime]] = []
        self.title_calls: list[tuple[UUID, datetime, datetime, int]] = []

    async def list_active_users(self, *, active_since: datetime, limit: int) -> list[ActiveUser]:
        self.active_user_calls.append({"active_since": active_since, "limit": limit})
        return self.users

    async def claim_report(
        self,
        *,
        report_id: UUID,
        user_id: UUID,
        kind: str,
        period_start: date,
        timezone: str,
        content_version: str,
        outbox_id: UUID,
    ) -> bool:
        self.claims.append(
            {
                "report_id": report_id,
                "user_id": user_id,
                "kind": kind,
                "period_start": period_start,
                "timezone": timezone,
                "content_version": content_version,
                "outbox_id": outbox_id,
            }
        )
        return (user_id, kind, period_start) not in self.existing

    async def get_report(self, report_id: UUID) -> DigestReport | None:
        if self.report is not None and self.report.id == report_id:
            return self.report
        return None

    async def complete_report(
        self, report_id: UUID, *, content: dict[str, object], summary_model: str | None
    ) -> bool:
        self.completed.append((report_id, content, summary_model))
        return True

    async def fail_report(self, report_id: UUID, *, error_code: str) -> bool:
        self.failed.append((report_id, error_code))
        return True

    async def count_done_between(self, user_id: UUID, *, start: datetime, end: datetime) -> int:
        self.done_calls.append((user_id, start, end))
        return self.done_count

    async def list_reports(
        self, user_id: UUID, *, kind: str | None, from_date: date | None, limit: int
    ) -> list[DigestReport]:
        self.list_calls.append(
            {"user_id": user_id, "kind": kind, "from_date": from_date, "limit": limit}
        )
        return self.listed

    async def requeue_failed_report(
        self, user_id: UUID, *, report_id: UUID, outbox_id: UUID
    ) -> DigestReport | None:
        self.requeue_calls.append(
            {"user_id": user_id, "report_id": report_id, "outbox_id": outbox_id}
        )
        return self.requeued

    async def count_captured_between(self, user_id: UUID, *, start: datetime, end: datetime) -> int:
        self.captured_calls.append((user_id, start, end))
        return self.captured_count

    async def list_done_titles_between(
        self, user_id: UUID, *, start: datetime, end: datetime, limit: int
    ) -> list[str]:
        self.title_calls.append((user_id, start, end, limit))
        return self.done_titles


class FakeCaptureRepository:
    """`CaptureRepository` の代わりに、Today の候補を返す fake。"""

    def __init__(self, candidates: Sequence[TodayCandidate] = ()) -> None:
        self.candidates = list(candidates)
        self.candidate_reads: list[UUID] = []
        self.by_ids_calls: list[list[UUID]] = []

    async def list_open_scenario_candidates(self, user_id: UUID) -> list[TodayCandidate]:
        self.candidate_reads.append(user_id)
        return self.candidates

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        self.by_ids_calls.append(list(capture_ids))
        due_by_id = {candidate.capture_id: candidate.due_at for candidate in self.candidates}
        # 順位の逆順で返し、service が順位どおりに並べ直すことを確かめる
        return [
            make_capture(capture_id, due_by_id[capture_id]) for capture_id in reversed(capture_ids)
        ]


def title_of(capture_id: UUID) -> str:
    return f"title-{capture_id.int}"


def make_capture(capture_id: UUID, due_at: datetime | None) -> Capture:
    return Capture(
        id=capture_id,
        user_id=TOKYO_USER.user_id,
        raw_text="本文は、ダイジェストに出さない",
        status=CAPTURE_STATUS_COMPLETED,
        idempotency_key=str(capture_id),
        request_hash="a" * 64,
        processing_generation=1,
        category="reminder",
        route="reminder",
        urgency="normal",
        confidence=None,
        policy_version=None,
        question_version=None,
        processed_at=CREATED,
        clarification_text=None,
        created_at=CREATED,
        updated_at=CREATED,
        scenario=CaptureScenario(
            route="reminder",
            status="accepted",
            title=title_of(capture_id),
            amount=None,
            remind_text=None,
            policy_version="v1",
            due_at=due_at,
        ),
    )


def make_candidate(capture_id: UUID, *, due_at: datetime | None = None) -> TodayCandidate:
    return TodayCandidate(
        capture_id=capture_id,
        urgency_score=Decimal("0.50"),
        due_at=due_at,
        created_at=CREATED,
    )


def make_report(
    *,
    kind: str = DIGEST_KIND_DAILY,
    status: str = DIGEST_STATUS_PENDING,
    period_start: date = date(2026, 11, 10),
    timezone: str = "Asia/Tokyo",
) -> DigestReport:
    return DigestReport(
        id=UUID(int=100),
        user_id=TOKYO_USER.user_id,
        kind=kind,
        period_start=period_start,
        timezone=timezone,
        status=status,
        content=None,
        content_version="daily-digest-v1",
        summary_model=None,
        error_code=None,
        generated_at=None,
        created_at=CREATED,
        updated_at=CREATED,
    )


class FakeSummarizer:
    """`ReviewSummarizer` の代わりに、呼び出しを記録して、決めた値か例外を返す fake。"""

    def __init__(
        self, result: str | Exception = "先週の要約", *, model_name: str = "test-model"
    ) -> None:
        self.result = result
        self.model_name = model_name
        self.calls: list[WeeklyReviewInput] = []

    async def summarize_week(self, review: WeeklyReviewInput) -> str:
        self.calls.append(review)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result
