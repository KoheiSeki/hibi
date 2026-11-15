import hashlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hibi.ai.classification import CAPTURE_QUESTION_VERSION
from hibi.ai.embedding import CAPTURE_EMBED_DIMENSIONS, CAPTURE_EMBED_VERSION, Embedding
from hibi.ai.fake_embedder import CAPTURE_EMBED_FAKE_MODEL
from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine, get_engine
from hibi.modules.captures.models import (
    CaptureEmbeddingModel,
    CaptureModel,
    CaptureScenarioModel,
    OutboxModel,
)
from hibi.modules.captures.policies import (
    CAPTURE_ROUTE_POLICY_VERSION,
    CAPTURE_SCENARIO_POLICY_VERSION,
    CAPTURE_SCENARIO_STATUS_PROPOSED,
    ScenarioProposal,
    propose_capture_scenario,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.types import (
    CAPTURE_PROCESSING_REQUESTED,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    Capture,
)

_HASH_A = "a" * 64
_HASH_B = "b" * 64

# 2026-11-10 15:00 JST
_NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)


def _database_url() -> str:
    return get_settings().database_url


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    if not _database_url():
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


async def _create_capture(
    repo: CaptureRepository,
    user_id: UUID,
    *,
    raw_text: str = "牛乳を買う",
    idempotency_key: str | None = None,
    request_hash: str = _HASH_A,
) -> Capture:
    return await repo.create_capture(
        user_id,
        capture_id=uuid7(),
        raw_text=raw_text,
        idempotency_key=idempotency_key or str(uuid4()),
        request_hash=request_hash,
        outbox_id=uuid7(),
    )


@pytest.mark.integration
async def test_owner_can_get_created_capture(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)

    created = await _create_capture(repo, user_id)
    found = await repo.get_by_id(user_id, capture_id=created.id)

    assert found is not None
    assert found.id == created.id
    assert found.user_id == user_id
    assert found.raw_text == "牛乳を買う"
    assert found.status == "pending"
    assert found.created_at.tzinfo is not None
    assert found.updated_at.tzinfo is not None


@pytest.mark.integration
async def test_other_user_get_by_id_returns_none(session: AsyncSession) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)

    created = await _create_capture(repo, owner_id)
    found = await repo.get_by_id(other_id, capture_id=created.id)

    assert found is None


@pytest.mark.integration
async def test_get_by_idempotency_key_is_owner_scoped(session: AsyncSession) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)
    key = "idem-key-owner-1"

    await _create_capture(repo, owner_id, idempotency_key=key)

    assert await repo.get_by_idempotency_key(owner_id, key=key) is not None
    assert await repo.get_by_idempotency_key(other_id, key=key) is None


@pytest.mark.integration
async def test_list_for_user_excludes_others_and_orders_newest_first(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)

    older = await _create_capture(repo, owner_id, raw_text="先に書いた")
    newer = await _create_capture(repo, owner_id, raw_text="後に書いた")
    await _create_capture(repo, other_id, raw_text="他人のメモ")

    items = await repo.list_for_user(owner_id, limit=10)

    assert [item.id for item in items] == [newer.id, older.id]
    assert all(item.user_id == owner_id for item in items)


@pytest.mark.integration
async def test_update_is_owner_scoped(session: AsyncSession) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)
    created = await _create_capture(repo, owner_id)

    updated = await repo.update_capture(owner_id, capture_id=created.id, raw_text="卵を買う")
    other = await repo.update_capture(other_id, capture_id=created.id, raw_text="hack")

    assert updated is not None
    assert updated.raw_text == "卵を買う"
    assert updated.updated_at >= created.updated_at
    assert other is None
    remaining = await repo.get_by_id(owner_id, capture_id=created.id)
    assert remaining is not None
    assert remaining.raw_text == "卵を買う"


@pytest.mark.integration
async def test_delete_is_owner_scoped(session: AsyncSession) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)
    created = await _create_capture(repo, owner_id)

    assert await repo.delete_capture(other_id, capture_id=created.id) is False
    assert await repo.get_by_id(owner_id, capture_id=created.id) is not None
    assert await repo.delete_capture(owner_id, capture_id=created.id) is True
    assert await repo.get_by_id(owner_id, capture_id=created.id) is None


@pytest.mark.integration
async def test_delete_capture_also_deletes_its_outbox_events(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    created = await _create_capture(repo, user_id)

    assert await repo.delete_capture(user_id, capture_id=created.id) is True

    remaining = await session.scalar(
        select(func.count()).select_from(OutboxModel).where(OutboxModel.aggregate_id == created.id)
    )
    assert remaining == 0


@pytest.mark.integration
async def test_duplicate_idempotency_key_raises_integrity_error(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    key = "idem-key-duplicate"

    await repo.create_capture(
        user_id,
        capture_id=uuid7(),
        raw_text="1件目",
        idempotency_key=key,
        request_hash=_HASH_A,
        outbox_id=uuid7(),
    )

    with pytest.raises(IntegrityError):
        await repo.create_capture(
            user_id,
            capture_id=uuid7(),
            raw_text="2件目",
            idempotency_key=key,
            request_hash=_HASH_B,
            outbox_id=uuid7(),
        )


@pytest.mark.integration
async def test_create_capture_writes_capture_and_outbox(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)

    created = await _create_capture(repo, user_id)
    outbox = await session.scalar(select(OutboxModel).where(OutboxModel.aggregate_id == created.id))

    assert outbox is not None
    assert outbox.user_id == user_id
    assert outbox.aggregate_type == "capture"
    assert outbox.event_type == CAPTURE_PROCESSING_REQUESTED
    assert outbox.processing_generation == 1
    assert outbox.status == OUTBOX_STATUS_PENDING
    assert created.status == CAPTURE_STATUS_PENDING


@pytest.mark.integration
async def test_failed_create_leaves_neither_capture_nor_outbox(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    key = "idem-key-rollback"
    created = await _create_capture(repo, user_id, idempotency_key=key)

    with pytest.raises(IntegrityError):
        await repo.create_capture(
            user_id,
            capture_id=uuid7(),
            raw_text="2件目",
            idempotency_key=key,
            request_hash=_HASH_B,
            outbox_id=uuid7(),
        )
    await session.rollback()

    capture_count = await session.scalar(
        text("SELECT count(*) FROM app.captures WHERE id = :id"),
        {"id": created.id},
    )
    outbox_count = await session.scalar(
        text("SELECT count(*) FROM app.outbox_events WHERE aggregate_id = :id"),
        {"id": created.id},
    )
    assert capture_count == 0
    assert outbox_count == 0


@pytest.mark.integration
async def test_list_pending_outbox_events_filters_orders_and_limits(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    now = datetime.now(UTC)

    oldest = await _create_capture(repo, user_id, raw_text="oldest")
    newer = await _create_capture(repo, user_id, raw_text="newer")
    published = await _create_capture(repo, user_id, raw_text="published")
    future = await _create_capture(repo, user_id, raw_text="future")

    await session.execute(
        update(OutboxModel)
        .where(OutboxModel.aggregate_id == oldest.id)
        .values(available_at=now - timedelta(minutes=2))
    )
    await session.execute(
        update(OutboxModel)
        .where(OutboxModel.aggregate_id == newer.id)
        .values(available_at=now - timedelta(minutes=1))
    )
    await session.execute(
        update(OutboxModel)
        .where(OutboxModel.aggregate_id == published.id)
        .values(
            status=OUTBOX_STATUS_PUBLISHED,
            available_at=now - timedelta(minutes=3),
        )
    )
    await session.execute(
        update(OutboxModel)
        .where(OutboxModel.aggregate_id == future.id)
        .values(available_at=now + timedelta(minutes=1))
    )

    first_page = await repo.list_pending_outbox_events(limit=1)
    all_available = await repo.list_pending_outbox_events(limit=20)

    assert [event.aggregate_id for event in first_page] == [oldest.id]
    assert [event.aggregate_id for event in all_available] == [oldest.id, newer.id]


@pytest.mark.integration
async def test_update_outbox_published_sets_timestamp_once(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    outbox = await session.scalar(select(OutboxModel).where(OutboxModel.aggregate_id == capture.id))
    assert outbox is not None

    first_update = await repo.update_outbox_published(outbox_id=outbox.id)
    second_update = await repo.update_outbox_published(outbox_id=outbox.id)
    await session.refresh(outbox)

    assert first_update is True
    assert second_update is False
    assert outbox.status == OUTBOX_STATUS_PUBLISHED
    assert outbox.published_at is not None


@pytest.mark.integration
@pytest.mark.parametrize(
    "capture_status",
    [CAPTURE_STATUS_PROCESSING, CAPTURE_STATUS_COMPLETED],
)
async def test_update_capture_rejects_non_editable_status(
    session: AsyncSession,
    capture_status: str,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await session.execute(
        update(CaptureModel).where(CaptureModel.id == capture.id).values(status=capture_status)
    )

    updated = await repo.update_capture(
        user_id,
        capture_id=capture.id,
        raw_text="更新後",
    )

    assert updated is None
    stored = await repo.get_by_id(user_id, capture_id=capture.id)
    assert stored is not None
    assert stored.raw_text == "牛乳を買う"


@pytest.mark.integration
async def test_retry_failed_capture_creates_next_generation_outbox(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_FAILED)
    )
    outbox_id = uuid7()

    retried = await repo.retry_failed_capture(
        user_id,
        capture_id=capture.id,
        outbox_id=outbox_id,
    )

    assert retried is not None
    assert retried.status == CAPTURE_STATUS_PENDING
    assert retried.processing_generation == 2
    outbox = await session.get(OutboxModel, outbox_id)
    assert outbox is not None
    assert outbox.aggregate_id == capture.id
    assert outbox.processing_generation == 2
    assert outbox.status == OUTBOX_STATUS_PENDING


@pytest.mark.integration
async def test_retry_non_failed_capture_does_not_create_outbox(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    before = (
        await session.scalars(select(OutboxModel).where(OutboxModel.aggregate_id == capture.id))
    ).all()

    retried = await repo.retry_failed_capture(
        user_id,
        capture_id=capture.id,
        outbox_id=uuid7(),
    )

    assert retried is None
    after = (
        await session.scalars(select(OutboxModel).where(OutboxModel.aggregate_id == capture.id))
    ).all()
    assert len(after) == len(before)


def _embedding(vector: tuple[float, ...] = (1, 0, 0, 0, 0, 0, 0, 0)) -> Embedding:
    return Embedding(
        vector=vector,
        model=CAPTURE_EMBED_FAKE_MODEL,
        dimensions=CAPTURE_EMBED_DIMENSIONS,
        version=CAPTURE_EMBED_VERSION,
    )


async def _complete_classification(
    repo: CaptureRepository,
    capture: Capture,
    *,
    processing_generation: int = 1,
    scenario: ScenarioProposal | None,
    embedding: Embedding | None = None,
    urgency_score: Decimal | None = None,
) -> Capture | None:
    return await repo.complete_capture_classification(
        capture_id=capture.id,
        processing_generation=processing_generation,
        category="reminder",
        route="reminder",
        urgency="normal",
        confidence=Decimal("0.9"),
        policy_version=CAPTURE_ROUTE_POLICY_VERSION,
        question_version=CAPTURE_QUESTION_VERSION,
        clarification_text=None,
        urgency_score=urgency_score,
        scenario=scenario,
        embedding=embedding,
    )


@pytest.mark.integration
async def test_complete_capture_inserts_proposed_scenario(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id, raw_text="明日の 9 時に起こして")
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_PROCESSING)
    )
    proposal = propose_capture_scenario(
        route="reminder", raw_text=capture.raw_text, now=_NOW, timezone="Asia/Tokyo"
    )

    completed = await _complete_classification(repo, capture, scenario=proposal)
    stored = await session.scalar(
        select(CaptureScenarioModel).where(CaptureScenarioModel.capture_id == capture.id)
    )

    assert completed is not None
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.status == CAPTURE_SCENARIO_STATUS_PROPOSED
    assert stored.title == "起こして"
    assert stored.remind_text == "明日の 9 時"
    assert stored.amount is None


@pytest.mark.integration
async def test_complete_capture_does_not_insert_scenario_for_other_generation(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_PROCESSING)
    )

    completed = await _complete_classification(
        repo,
        capture,
        processing_generation=2,
        scenario=propose_capture_scenario(
            route="shopping", raw_text="牛乳を買う", now=_NOW, timezone="Asia/Tokyo"
        ),
    )
    stored = await session.scalar(
        select(CaptureScenarioModel).where(CaptureScenarioModel.capture_id == capture.id)
    )

    assert completed is None
    assert stored is None


@pytest.mark.integration
async def test_complete_capture_without_scenario_inserts_no_row(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_PROCESSING)
    )

    completed = await _complete_classification(repo, capture, scenario=None)
    stored = await session.scalar(
        select(CaptureScenarioModel).where(CaptureScenarioModel.capture_id == capture.id)
    )

    assert completed is not None
    assert stored is None


@pytest.mark.integration
async def test_complete_capture_saves_urgency_score_and_due_at(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id, raw_text="明日の 9 時に起こして")
    await _mark_processing(session, capture.id)
    proposal = propose_capture_scenario(
        route="reminder", raw_text=capture.raw_text, now=_NOW, timezone="Asia/Tokyo"
    )

    completed = await _complete_classification(
        repo, capture, scenario=proposal, urgency_score=Decimal("0.50")
    )
    urgency_score = await session.scalar(
        select(CaptureModel.urgency_score).where(CaptureModel.id == capture.id)
    )
    stored = await session.scalar(
        select(CaptureScenarioModel).where(CaptureScenarioModel.capture_id == capture.id)
    )

    assert completed is not None
    assert urgency_score == Decimal("0.50")
    assert stored is not None
    assert stored.due_at == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
    assert stored.done_at is None


@pytest.mark.integration
async def test_complete_capture_saves_a_null_urgency_score(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await _mark_processing(session, capture.id)

    completed = await _complete_classification(repo, capture, scenario=None, urgency_score=None)
    urgency_score = await session.scalar(
        select(CaptureModel.urgency_score).where(CaptureModel.id == capture.id)
    )

    assert completed is not None
    assert urgency_score is None


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _mark_processing(session: AsyncSession, capture_id: UUID) -> None:
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture_id)
        .values(status=CAPTURE_STATUS_PROCESSING)
    )


async def _completed_with_scenario(
    session: AsyncSession,
    repo: CaptureRepository,
    user_id: UUID,
    *,
    raw_text: str = "牛乳を買う",
    route: str = "shopping",
    urgency_score: Decimal | None = Decimal("0.50"),
) -> Capture:
    capture = await _create_capture(repo, user_id, raw_text=raw_text)
    await _mark_processing(session, capture.id)
    proposal = propose_capture_scenario(
        route=route, raw_text=raw_text, now=_NOW, timezone="Asia/Tokyo"
    )
    await _complete_classification(repo, capture, scenario=proposal, urgency_score=urgency_score)
    return capture


@pytest.mark.integration
async def test_list_open_scenario_candidates_returns_only_undone_completed_scenarios_of_the_owner(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)
    open_capture = await _completed_with_scenario(session, repo, owner_id)
    done_capture = await _completed_with_scenario(session, repo, owner_id, raw_text="卵を買う")
    await repo.set_scenario_done(owner_id, capture_id=done_capture.id, done=True)
    # シナリオの無い completed
    no_scenario = await _create_capture(repo, owner_id, raw_text="あとで読む記事")
    await _mark_processing(session, no_scenario.id)
    await _complete_classification(repo, no_scenario, scenario=None)
    # completed でない Capture に、シナリオの行だけがある
    pending = await _create_capture(repo, owner_id, raw_text="パンを買う")
    session.add(
        CaptureScenarioModel(
            capture_id=pending.id,
            user_id=owner_id,
            route="shopping",
            status=CAPTURE_SCENARIO_STATUS_PROPOSED,
            title="パン",
            policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
        )
    )
    await session.flush()
    # 別ユーザー
    await _completed_with_scenario(session, repo, other_id)

    candidates = await repo.list_open_scenario_candidates(owner_id)

    assert [candidate.capture_id for candidate in candidates] == [open_capture.id]
    assert candidates[0].urgency_score == Decimal("0.50")
    assert candidates[0].due_at is None
    assert candidates[0].created_at == open_capture.created_at


@pytest.mark.integration
async def test_list_open_scenario_candidates_carries_the_deadline_and_a_null_urgency_score(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    reminder = await _completed_with_scenario(
        session,
        repo,
        user_id,
        raw_text="明日の 9 時に起こして",
        route="reminder",
        urgency_score=None,
    )

    candidates = await repo.list_open_scenario_candidates(user_id)

    assert [candidate.capture_id for candidate in candidates] == [reminder.id]
    assert candidates[0].urgency_score is None
    assert candidates[0].due_at == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)


@pytest.mark.integration
async def test_list_open_scenario_candidates_is_empty_without_scenarios(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)

    assert await CaptureRepository(session).list_open_scenario_candidates(user_id) == []


@pytest.mark.integration
async def test_set_scenario_done_sets_and_clears_the_completion_time(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _completed_with_scenario(session, repo, user_id)
    done_at_query = select(CaptureScenarioModel.done_at).where(
        CaptureScenarioModel.capture_id == capture.id
    )

    assert await repo.set_scenario_done(user_id, capture_id=capture.id, done=True) is True
    assert await session.scalar(done_at_query) is not None

    assert await repo.set_scenario_done(user_id, capture_id=capture.id, done=False) is True
    assert await session.scalar(done_at_query) is None


@pytest.mark.integration
async def test_set_scenario_done_keeps_the_first_completion_time(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _completed_with_scenario(session, repo, user_id)
    first_done_at = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    # 同じ transaction の now() は変わらないため、過去の時刻を直接入れて上書きを検出する
    await session.execute(
        update(CaptureScenarioModel)
        .where(CaptureScenarioModel.capture_id == capture.id)
        .values(done_at=first_done_at)
    )

    assert await repo.set_scenario_done(user_id, capture_id=capture.id, done=True) is True
    stored = await session.scalar(
        select(CaptureScenarioModel.done_at).where(CaptureScenarioModel.capture_id == capture.id)
    )

    assert stored == first_done_at


@pytest.mark.integration
async def test_set_scenario_done_returns_false_for_other_owners_and_missing_scenarios(
    session: AsyncSession,
) -> None:
    owner_id, other_id = uuid4(), uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repo = CaptureRepository(session)
    capture = await _completed_with_scenario(session, repo, owner_id)
    no_scenario = await _create_capture(repo, owner_id, raw_text="あとで読む記事")

    assert await repo.set_scenario_done(other_id, capture_id=capture.id, done=True) is False
    assert await repo.set_scenario_done(owner_id, capture_id=no_scenario.id, done=True) is False
    assert await repo.set_scenario_done(owner_id, capture_id=uuid4(), done=True) is False


@pytest.mark.integration
async def test_complete_capture_inserts_embedding_for_the_owner(session: AsyncSession) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id, raw_text="牛乳を買う")
    await _mark_processing(session, capture.id)
    embedding = _embedding()

    completed = await _complete_classification(repo, capture, scenario=None, embedding=embedding)
    stored = await session.get(CaptureEmbeddingModel, capture.id)

    assert completed is not None
    assert stored is not None
    assert stored.user_id == user_id
    assert stored.content_text == "牛乳を買う"
    assert stored.content_hash == _content_hash("牛乳を買う")
    assert list(stored.embedding) == list(embedding.vector)
    assert stored.embedding_model == CAPTURE_EMBED_FAKE_MODEL
    assert stored.embedding_dimensions == CAPTURE_EMBED_DIMENSIONS
    assert stored.embedding_version == CAPTURE_EMBED_VERSION


@pytest.mark.integration
async def test_complete_capture_does_not_insert_embedding_for_other_generation(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await _mark_processing(session, capture.id)

    completed = await _complete_classification(
        repo,
        capture,
        processing_generation=2,
        scenario=None,
        embedding=_embedding(),
    )
    stored = await session.get(CaptureEmbeddingModel, capture.id)

    assert completed is None
    assert stored is None


@pytest.mark.integration
async def test_complete_capture_without_embedding_inserts_no_embedding_row(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id)
    await _mark_processing(session, capture.id)

    completed = await _complete_classification(repo, capture, scenario=None)
    stored = await session.get(CaptureEmbeddingModel, capture.id)

    assert completed is not None
    assert stored is None


@pytest.mark.integration
async def test_complete_capture_keeps_embedding_when_content_hash_matches(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id, raw_text="牛乳を買う")
    await _mark_processing(session, capture.id)
    kept = (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    session.add(
        CaptureEmbeddingModel(
            capture_id=capture.id,
            user_id=user_id,
            content_text=capture.raw_text,
            content_hash=_content_hash(capture.raw_text),
            embedding=list(kept),
            embedding_model=CAPTURE_EMBED_FAKE_MODEL,
            embedding_dimensions=CAPTURE_EMBED_DIMENSIONS,
            embedding_version=CAPTURE_EMBED_VERSION,
        )
    )
    await session.flush()

    completed = await _complete_classification(
        repo,
        capture,
        scenario=None,
        embedding=_embedding((1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)),
    )
    stored = await session.get(CaptureEmbeddingModel, capture.id)

    assert completed is not None
    assert stored is not None
    assert list(stored.embedding) == list(kept)


@pytest.mark.integration
async def test_complete_capture_replaces_embedding_when_content_hash_differs(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    capture = await _create_capture(repo, user_id, raw_text="牛乳を買う")
    await _mark_processing(session, capture.id)
    session.add(
        CaptureEmbeddingModel(
            capture_id=capture.id,
            user_id=user_id,
            content_text="古い本文",
            content_hash="b" * 64,
            embedding=[0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            embedding_model=CAPTURE_EMBED_FAKE_MODEL,
            embedding_dimensions=CAPTURE_EMBED_DIMENSIONS,
            embedding_version=CAPTURE_EMBED_VERSION,
        )
    )
    await session.flush()
    replacement = _embedding()

    completed = await _complete_classification(repo, capture, scenario=None, embedding=replacement)
    stored = await session.get(CaptureEmbeddingModel, capture.id)

    assert completed is not None
    assert stored is not None
    assert stored.content_text == "牛乳を買う"
    assert stored.content_hash == _content_hash("牛乳を買う")
    assert list(stored.embedding) == list(replacement.vector)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_search_documents_returns_only_completed_rows_of_the_owner(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repository = CaptureRepository(session=session)

    completed = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    pending = await _create_capture(repository, owner_id, raw_text="あとで読む記事")
    other = await _create_capture(repository, other_id, raw_text="牛乳を買う")
    for capture_id in (completed.id, other.id):
        await session.execute(
            update(CaptureModel)
            .where(CaptureModel.id == capture_id)
            .values(status=CAPTURE_STATUS_COMPLETED)
        )
    session.add(
        CaptureEmbeddingModel(
            capture_id=completed.id,
            user_id=owner_id,
            content_text="牛乳を買う",
            content_hash=hashlib.sha256("牛乳を買う".encode()).hexdigest(),
            embedding=[1.0] + [0.0] * (CAPTURE_EMBED_DIMENSIONS - 1),
            embedding_model=CAPTURE_EMBED_FAKE_MODEL,
            embedding_dimensions=CAPTURE_EMBED_DIMENSIONS,
            embedding_version=CAPTURE_EMBED_VERSION,
        )
    )
    await session.flush()

    documents = await repository.list_search_documents(owner_id)

    assert [document.capture_id for document in documents] == [completed.id]
    assert pending.id not in {document.capture_id for document in documents}
    assert other.id not in {document.capture_id for document in documents}
    assert documents[0].text == "牛乳を買う"
    assert documents[0].embedding is not None
    assert documents[0].embedding.vector[0] == 1.0
    assert documents[0].embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert documents[0].embedding.version == CAPTURE_EMBED_VERSION


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_search_documents_keeps_rows_without_an_embedding(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    await _insert_auth_user(session, owner_id)
    repository = CaptureRepository(session=session)

    capture = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_COMPLETED)
    )
    await session.flush()

    documents = await repository.list_search_documents(owner_id)

    assert [document.capture_id for document in documents] == [capture.id]
    assert documents[0].embedding is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_captures_by_ids_loads_the_scenario_for_the_owner(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repository = CaptureRepository(session=session)

    first = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    second = await _create_capture(repository, owner_id, raw_text="ランチ 1200 円")
    other = await _create_capture(repository, other_id, raw_text="牛乳を買う")
    session.add(
        CaptureScenarioModel(
            capture_id=first.id,
            user_id=owner_id,
            route="shopping",
            status=CAPTURE_SCENARIO_STATUS_PROPOSED,
            title="牛乳",
            amount=None,
            remind_text=None,
            policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
        )
    )
    await session.flush()

    captures = await repository.list_captures_by_ids(
        owner_id, capture_ids=[second.id, first.id, other.id]
    )

    by_id = {capture.id: capture for capture in captures}
    assert set(by_id) == {first.id, second.id}
    first_scenario = by_id[first.id].scenario
    assert first_scenario is not None
    assert first_scenario.title == "牛乳"
    assert by_id[second.id].scenario is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_captures_by_ids_returns_an_empty_list_without_ids(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    await _insert_auth_user(session, owner_id)
    repository = CaptureRepository(session=session)

    assert await repository.list_captures_by_ids(owner_id, capture_ids=[]) == []
