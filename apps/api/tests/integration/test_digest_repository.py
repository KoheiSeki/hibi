from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine, get_engine
from hibi.modules.captures.models import CaptureModel, CaptureScenarioModel
from hibi.modules.captures.policies import (
    CAPTURE_SCENARIO_POLICY_VERSION,
    CAPTURE_SCENARIO_STATUS_PROPOSED,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.models import DigestReportModel
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.types import (
    DIGEST_AGGREGATE_TYPE,
    DIGEST_GENERATION_REQUESTED,
    DIGEST_KIND_DAILY,
    DIGEST_KIND_WEEKLY,
    DIGEST_STATUS_FAILED,
    DIGEST_STATUS_PENDING,
    DIGEST_STATUS_READY,
)
from hibi.modules.outbox.models import OutboxModel
from hibi.modules.outbox.types import OUTBOX_STATUS_PENDING, OUTBOX_STATUS_PUBLISHED

_DAY = date(2026, 11, 10)
# 開発用の DB に、実際の時刻の行が残っていても、数えないように、遠い未来の日時を使う
_NOW = datetime(2099, 1, 15, tzinfo=UTC)
_ACTIVE_SINCE = _NOW - timedelta(days=14)
_CONTENT = {"items": [], "overdueCount": 0, "dueTodayCount": 0, "doneYesterdayCount": 0}


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    if not get_settings().database_url:
        pytest.skip("HIBI_DATABASE_URL is not configured")
    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                yield session
            finally:
                await session.rollback()
    except OperationalError:
        pytest.skip("PostgreSQL is not reachable at HIBI_DATABASE_URL")
    finally:
        await dispose_engine()


async def _insert_auth_user(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(text("INSERT INTO auth.users (id) VALUES (:id)"), {"id": user_id})


async def _claim(
    repo: DigestRepository,
    user_id: UUID,
    *,
    report_id: UUID | None = None,
    kind: str = DIGEST_KIND_DAILY,
    period_start: date = _DAY,
) -> bool:
    return await repo.claim_report(
        report_id=report_id or uuid7(),
        user_id=user_id,
        kind=kind,
        period_start=period_start,
        timezone="Asia/Tokyo",
        content_version="daily-digest-v1",
        outbox_id=uuid7(),
    )


async def _outbox_count(session: AsyncSession, user_id: UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).select_from(OutboxModel).where(OutboxModel.user_id == user_id)
        )
        or 0
    )


@pytest.mark.integration
async def test_claim_report_inserts_one_pending_row_and_one_outbox_event(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    report_id = uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)

    first = await _claim(repo, user_id, report_id=report_id)
    second = await _claim(repo, user_id)

    assert (first, second) == (True, False)
    report = await repo.get_report(report_id)
    assert report is not None
    assert report.user_id == user_id
    assert report.kind == DIGEST_KIND_DAILY
    assert report.period_start == _DAY
    assert report.timezone == "Asia/Tokyo"
    assert report.status == DIGEST_STATUS_PENDING
    assert report.content is None
    assert report.content_version == "daily-digest-v1"
    outbox = await session.scalar(select(OutboxModel).where(OutboxModel.user_id == user_id))
    assert outbox is not None
    assert outbox.aggregate_type == DIGEST_AGGREGATE_TYPE
    assert outbox.aggregate_id == report_id
    assert outbox.event_type == DIGEST_GENERATION_REQUESTED
    assert await _outbox_count(session, user_id) == 1


@pytest.mark.integration
async def test_claim_report_keeps_separate_rows_per_user_kind_and_period(
    session: AsyncSession,
) -> None:
    user_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, user_id)
    await _insert_auth_user(session, other_id)
    repo = DigestRepository(session)

    results = [
        await _claim(repo, user_id),
        await _claim(repo, user_id, period_start=date(2026, 11, 11)),
        await _claim(repo, user_id, kind=DIGEST_KIND_WEEKLY),
        await _claim(repo, other_id),
    ]

    assert results == [True, True, True, True]
    assert await _outbox_count(session, user_id) == 3


@pytest.mark.integration
async def test_claim_report_rejects_an_unknown_kind(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)

    with pytest.raises(IntegrityError):
        await _claim(DigestRepository(session), user_id, kind="monthly")


@pytest.mark.integration
async def test_complete_report_marks_a_pending_report_ready_once(session: AsyncSession) -> None:
    user_id = uuid4()
    report_id = uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    await _claim(repo, user_id, report_id=report_id)

    first = await repo.complete_report(report_id, content=_CONTENT, summary_model=None)
    second = await repo.complete_report(report_id, content={"other": 1}, summary_model=None)

    assert (first, second) == (True, False)
    report = await repo.get_report(report_id)
    assert report is not None
    assert report.status == DIGEST_STATUS_READY
    assert report.content == _CONTENT
    assert report.generated_at is not None
    assert report.error_code is None


@pytest.mark.integration
async def test_fail_report_marks_a_pending_report_failed_and_keeps_the_reason(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    report_id = uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    await _claim(repo, user_id, report_id=report_id)

    failed = await repo.fail_report(report_id, error_code="review_provider_error")
    completed_after = await repo.complete_report(report_id, content=_CONTENT, summary_model=None)

    assert (failed, completed_after) == (True, False)
    report = await repo.get_report(report_id)
    assert report is not None
    assert report.status == DIGEST_STATUS_FAILED
    assert report.error_code == "review_provider_error"
    assert report.content is None


@pytest.mark.integration
async def test_fail_report_does_not_overwrite_a_ready_report(session: AsyncSession) -> None:
    user_id = uuid4()
    report_id = uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    await _claim(repo, user_id, report_id=report_id)
    await repo.complete_report(report_id, content=_CONTENT, summary_model=None)

    assert await repo.fail_report(report_id, error_code="late_failure") is False
    report = await repo.get_report(report_id)
    assert report is not None
    assert report.status == DIGEST_STATUS_READY


@pytest.mark.integration
async def test_get_report_returns_none_for_a_missing_id(session: AsyncSession) -> None:
    assert await DigestRepository(session).get_report(uuid7()) is None


async def _capture_created_at(session: AsyncSession, user_id: UUID, created_at: datetime) -> UUID:
    capture = await CaptureRepository(session).create_capture(
        user_id,
        capture_id=uuid7(),
        raw_text="牛乳を買う",
        idempotency_key=str(uuid4()),
        request_hash="a" * 64,
        outbox_id=uuid7(),
    )
    await session.execute(
        update(CaptureModel).where(CaptureModel.id == capture.id).values(created_at=created_at)
    )
    return capture.id


async def _scenario_done_at(
    session: AsyncSession, user_id: UUID, done_at: datetime | None, *, title: str = "牛乳"
) -> None:
    capture_id = await _capture_created_at(session, user_id, _NOW)
    session.add(
        CaptureScenarioModel(
            capture_id=capture_id,
            user_id=user_id,
            route="shopping",
            status=CAPTURE_SCENARIO_STATUS_PROPOSED,
            title=title,
            policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
            done_at=done_at,
        )
    )
    await session.flush()


@pytest.mark.integration
async def test_list_active_users_returns_only_users_with_a_capture_since_the_given_time(
    session: AsyncSession,
) -> None:
    recent_id, boundary_id, stale_id, empty_id = uuid4(), uuid4(), uuid4(), uuid4()
    for user_id in (recent_id, boundary_id, stale_id, empty_id):
        await _insert_auth_user(session, user_id)
    await _capture_created_at(session, recent_id, _NOW - timedelta(days=1))
    await _capture_created_at(session, boundary_id, _ACTIVE_SINCE)
    await _capture_created_at(session, stale_id, _ACTIVE_SINCE - timedelta(seconds=1))

    users = await DigestRepository(session).list_active_users(active_since=_ACTIVE_SINCE, limit=100)

    # 境界ちょうどの Capture は対象に入る。Capture が無い利用者と、古いだけの利用者は入らない
    assert {user.user_id for user in users} == {recent_id, boundary_id}


@pytest.mark.integration
async def test_list_active_users_returns_a_user_once_however_many_captures_it_has(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    for days in (1, 2, 3):
        await _capture_created_at(session, user_id, _NOW - timedelta(days=days))

    users = await DigestRepository(session).list_active_users(active_since=_ACTIVE_SINCE, limit=100)

    assert [user.user_id for user in users] == [user_id]


@pytest.mark.integration
async def test_list_active_users_reads_the_profile_timezone(session: AsyncSession) -> None:
    tokyo_id, new_york_id = uuid4(), uuid4()
    for user_id, timezone in ((tokyo_id, "Asia/Tokyo"), (new_york_id, "America/New_York")):
        await _insert_auth_user(session, user_id)
        # 既定値に頼らず、利用者ごとに timezone を決める
        await session.execute(
            text("UPDATE app.profiles SET timezone = :timezone WHERE user_id = :id"),
            {"timezone": timezone, "id": user_id},
        )
        await _capture_created_at(session, user_id, _NOW)

    users = await DigestRepository(session).list_active_users(active_since=_ACTIVE_SINCE, limit=100)

    assert {user.user_id: user.timezone for user in users} == {
        tokyo_id: "Asia/Tokyo",
        new_york_id: "America/New_York",
    }


@pytest.mark.integration
async def test_list_active_users_orders_by_user_id_and_applies_the_limit(
    session: AsyncSession,
) -> None:
    user_ids = sorted(uuid4() for _ in range(3))
    for user_id in user_ids:
        await _insert_auth_user(session, user_id)
        await _capture_created_at(session, user_id, _NOW)

    users = await DigestRepository(session).list_active_users(active_since=_ACTIVE_SINCE, limit=2)

    assert [user.user_id for user in users] == user_ids[:2]


@pytest.mark.integration
async def test_count_done_between_counts_a_half_open_range(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    start = datetime(2099, 1, 10, tzinfo=UTC)
    end = start + timedelta(days=1)
    for done_at in (
        start - timedelta(seconds=1),  # 範囲の前
        start,  # 始まりちょうど。数える
        start + timedelta(hours=12),  # 範囲の中。数える
        end,  # 終わりちょうど。次の期間の分なので数えない
    ):
        await _scenario_done_at(session, user_id, done_at)

    count = await DigestRepository(session).count_done_between(user_id, start=start, end=end)

    assert count == 2


@pytest.mark.integration
async def test_count_done_between_ignores_other_users_and_undone_scenarios(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    start = datetime(2099, 1, 10, tzinfo=UTC)
    end = start + timedelta(days=1)
    await _scenario_done_at(session, owner_id, start + timedelta(hours=1))
    await _scenario_done_at(session, owner_id, None)  # 未完了
    await _scenario_done_at(session, other_id, start + timedelta(hours=1))  # 別ユーザー

    repo = DigestRepository(session)

    assert await repo.count_done_between(owner_id, start=start, end=end) == 1
    assert await repo.count_done_between(uuid4(), start=start, end=end) == 0


@pytest.mark.integration
async def test_count_captured_between_counts_a_half_open_range_of_the_owner(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    start = datetime(2099, 1, 5, tzinfo=UTC)
    end = start + timedelta(days=7)
    for created_at in (
        start - timedelta(seconds=1),  # 範囲の前
        start,  # 始まりちょうど。数える
        start + timedelta(days=3),  # 範囲の中。数える
        end,  # 終わりちょうど。次の週の分なので数えない
    ):
        await _capture_created_at(session, owner_id, created_at)
    await _capture_created_at(session, other_id, start + timedelta(days=1))  # 別ユーザー

    repo = DigestRepository(session)

    assert await repo.count_captured_between(owner_id, start=start, end=end) == 2
    assert await repo.count_captured_between(uuid4(), start=start, end=end) == 0


@pytest.mark.integration
async def test_list_done_titles_between_returns_the_titles_done_in_the_range_in_order(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    start = datetime(2099, 1, 5, tzinfo=UTC)
    end = start + timedelta(days=7)
    # 完了にした順と、登録した順を、変えておく
    await _scenario_done_at(session, owner_id, start + timedelta(days=2), title="二番目")
    await _scenario_done_at(session, owner_id, start + timedelta(days=1), title="一番目")
    await _scenario_done_at(session, owner_id, start + timedelta(days=3), title="三番目")
    await _scenario_done_at(session, owner_id, end, title="範囲の外")
    await _scenario_done_at(session, owner_id, None, title="未完了")
    await _scenario_done_at(session, other_id, start + timedelta(days=1), title="他人")

    repo = DigestRepository(session)

    titles = await repo.list_done_titles_between(owner_id, start=start, end=end, limit=10)
    limited = await repo.list_done_titles_between(owner_id, start=start, end=end, limit=2)

    # 完了にした順。範囲の外、未完了、他人のシナリオは入らない
    assert titles == ["一番目", "二番目", "三番目"]
    assert limited == ["一番目", "二番目"]


@pytest.mark.integration
async def test_list_reports_is_owner_scoped_newest_first_and_filtered(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = DigestRepository(session)
    for kind, period_start in (
        (DIGEST_KIND_DAILY, date(2026, 11, 9)),
        (DIGEST_KIND_DAILY, date(2026, 11, 11)),
        (DIGEST_KIND_DAILY, date(2026, 11, 10)),
        (DIGEST_KIND_WEEKLY, date(2026, 11, 2)),
    ):
        await _claim(repo, owner_id, kind=kind, period_start=period_start)
    await _claim(repo, other_id, period_start=date(2026, 11, 12))  # 別ユーザー

    async def periods(**kwargs: object) -> list[tuple[str, date]]:
        reports = await repo.list_reports(owner_id, **kwargs)  # type: ignore[arg-type]
        return [(report.kind, report.period_start) for report in reports]

    # 期間の日付の新しい順。別ユーザーの行は入らない
    assert await periods(kind=None, from_date=None, limit=10) == [
        (DIGEST_KIND_DAILY, date(2026, 11, 11)),
        (DIGEST_KIND_DAILY, date(2026, 11, 10)),
        (DIGEST_KIND_DAILY, date(2026, 11, 9)),
        (DIGEST_KIND_WEEKLY, date(2026, 11, 2)),
    ]
    assert await periods(kind=DIGEST_KIND_WEEKLY, from_date=None, limit=10) == [
        (DIGEST_KIND_WEEKLY, date(2026, 11, 2)),
    ]
    # from_date は下限で、その日を含む
    assert await periods(kind=None, from_date=date(2026, 11, 10), limit=10) == [
        (DIGEST_KIND_DAILY, date(2026, 11, 11)),
        (DIGEST_KIND_DAILY, date(2026, 11, 10)),
    ]
    assert await periods(kind=None, from_date=None, limit=2) == [
        (DIGEST_KIND_DAILY, date(2026, 11, 11)),
        (DIGEST_KIND_DAILY, date(2026, 11, 10)),
    ]


@pytest.mark.integration
async def test_requeue_failed_report_moves_it_to_pending_and_adds_one_outbox_event(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    report_id = uuid7()
    outbox_id = uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    await _claim(repo, user_id, report_id=report_id)
    await repo.fail_report(report_id, error_code="generation_failed")
    outbox_before = await _outbox_count(session, user_id)

    report = await repo.requeue_failed_report(user_id, report_id=report_id, outbox_id=outbox_id)

    assert report is not None
    assert report.id == report_id
    assert report.status == DIGEST_STATUS_PENDING
    # 前回の失敗の理由は、もう当てはまらないので消す
    assert report.error_code is None
    assert await _outbox_count(session, user_id) == outbox_before + 1
    event = await session.get(OutboxModel, outbox_id)
    assert event is not None
    assert event.aggregate_type == DIGEST_AGGREGATE_TYPE
    assert event.event_type == DIGEST_GENERATION_REQUESTED
    assert event.aggregate_id == report_id


@pytest.mark.integration
async def test_requeue_failed_report_leaves_a_report_that_is_not_failed(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    pending_id, ready_id = uuid7(), uuid7()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    await _claim(repo, user_id, report_id=pending_id, period_start=date(2026, 11, 10))
    await _claim(repo, user_id, report_id=ready_id, period_start=date(2026, 11, 11))
    await repo.complete_report(ready_id, content=_CONTENT, summary_model=None)
    outbox_before = await _outbox_count(session, user_id)

    for report_id in (pending_id, ready_id):
        requeued = await repo.requeue_failed_report(user_id, report_id=report_id, outbox_id=uuid7())
        assert requeued is None

    assert await _outbox_count(session, user_id) == outbox_before
    ready = await repo.get_report(ready_id)
    assert ready is not None
    assert ready.status == DIGEST_STATUS_READY


@pytest.mark.integration
async def test_requeue_failed_report_does_not_touch_another_owner(session: AsyncSession) -> None:
    owner_id, other_id = uuid4(), uuid4()
    report_id = uuid7()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = DigestRepository(session)
    await _claim(repo, owner_id, report_id=report_id)
    await repo.fail_report(report_id, error_code="generation_failed")

    requeued = await repo.requeue_failed_report(other_id, report_id=report_id, outbox_id=uuid7())

    assert requeued is None
    report = await repo.get_report(report_id)
    assert report is not None
    assert report.status == DIGEST_STATUS_FAILED
    assert await _outbox_count(session, other_id) == 0


# 止まった pending の回復のテスト。開発用の DB に残っている実際の行を数えないよう、
# どの行の updated_at よりも古い、遠い過去の時刻を使う
_RECOVERY_NOW = datetime(2000, 1, 1, 0, 10, tzinfo=UTC)
_STALLED_BEFORE = _RECOVERY_NOW - timedelta(minutes=10)


async def _claim_stalled(
    session: AsyncSession,
    repo: DigestRepository,
    user_id: UUID,
    *,
    period_start: date,
    status: str = DIGEST_STATUS_PENDING,
    minutes_ago: int = 11,
    outbox_published: bool = True,
) -> UUID:
    """行を作り、状態と updated_at を置き換える。作ったときの outbox は、既定で配送済みにする。"""

    report_id = uuid7()
    await _claim(repo, user_id, report_id=report_id, period_start=period_start)
    await session.execute(
        update(DigestReportModel)
        .where(DigestReportModel.id == report_id)
        .values(status=status, updated_at=_RECOVERY_NOW - timedelta(minutes=minutes_ago))
    )
    if outbox_published:
        await session.execute(
            update(OutboxModel)
            .where(OutboxModel.aggregate_id == report_id)
            .values(status=OUTBOX_STATUS_PUBLISHED, published_at=func.now())
        )
    return report_id


async def _report_outbox_events(session: AsyncSession, report_id: UUID) -> list[OutboxModel]:
    return list(
        (
            await session.scalars(
                select(OutboxModel)
                .where(OutboxModel.aggregate_id == report_id)
                .order_by(OutboxModel.created_at, OutboxModel.id)
            )
        ).all()
    )


class _OutboxIds:
    """回復が発行した outbox の id を、順に記録する。"""

    def __init__(self) -> None:
        self.issued: list[UUID] = []

    def __call__(self) -> UUID:
        outbox_id = uuid7()
        self.issued.append(outbox_id)
        return outbox_id


@pytest.mark.integration
async def test_requeue_stalled_reports_adds_an_outbox_event_for_old_pending_rows_only(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    stalled_id = await _claim_stalled(session, repo, user_id, period_start=date(2026, 11, 1))
    fresh_id = await _claim_stalled(
        session, repo, user_id, period_start=date(2026, 11, 2), minutes_ago=9
    )
    ready_id = await _claim_stalled(
        session, repo, user_id, period_start=date(2026, 11, 3), status=DIGEST_STATUS_READY
    )
    failed_id = await _claim_stalled(
        session, repo, user_id, period_start=date(2026, 11, 4), status=DIGEST_STATUS_FAILED
    )
    outbox_ids = _OutboxIds()

    requeued = await repo.requeue_stalled_reports(
        stalled_before=_STALLED_BEFORE, outbox_id_factory=outbox_ids
    )

    assert requeued == 1
    events = await _report_outbox_events(session, stalled_id)
    assert len(events) == 2
    new_event = next(event for event in events if event.status == OUTBOX_STATUS_PENDING)
    assert outbox_ids.issued == [new_event.id]
    assert new_event.user_id == user_id
    assert new_event.aggregate_type == DIGEST_AGGREGATE_TYPE
    assert new_event.event_type == DIGEST_GENERATION_REQUESTED
    for report_id in (fresh_id, ready_id, failed_id):
        assert len(await _report_outbox_events(session, report_id)) == 1


@pytest.mark.integration
async def test_requeue_stalled_reports_restarts_the_wait_from_the_requeue(
    session: AsyncSession,
) -> None:
    # updated_at を進めないと、job が動き出す前の、5 分後の次の回復が、同じ行に
    # もう一度 outbox を足してしまう
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    report_id = await _claim_stalled(session, repo, user_id, period_start=date(2026, 11, 1))

    await repo.requeue_stalled_reports(
        stalled_before=_STALLED_BEFORE, outbox_id_factory=_OutboxIds()
    )

    row = await session.get(DigestReportModel, report_id, populate_existing=True)
    assert row is not None
    assert row.status == DIGEST_STATUS_PENDING
    assert row.updated_at > _RECOVERY_NOW


@pytest.mark.integration
async def test_requeue_stalled_reports_does_not_stack_on_an_undelivered_outbox_event(
    session: AsyncSession,
) -> None:
    # relay が止まっているだけなら、未配送の outbox が届けば job が動くので、重ねて足さない
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = DigestRepository(session)
    report_id = await _claim_stalled(
        session, repo, user_id, period_start=date(2026, 11, 1), outbox_published=False
    )
    outbox_ids = _OutboxIds()

    requeued = await repo.requeue_stalled_reports(
        stalled_before=_STALLED_BEFORE, outbox_id_factory=outbox_ids
    )

    assert requeued == 0
    assert outbox_ids.issued == []
    assert len(await _report_outbox_events(session, report_id)) == 1
