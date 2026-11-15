from collections.abc import AsyncGenerator
from datetime import date
from uuid import UUID, uuid4, uuid7

import pytest
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
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine, get_engine
from hibi.modules.captures.models import OutboxModel

_DAY = date(2026, 11, 10)
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
