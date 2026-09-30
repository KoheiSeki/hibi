from collections.abc import AsyncGenerator
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine, get_engine
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.types import Capture

_HASH_A = "a" * 64
_HASH_B = "b" * 64


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
        id=uuid7(),
        raw_text=raw_text,
        idempotency_key=idempotency_key or str(uuid4()),
        request_hash=request_hash,
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
async def test_duplicate_idempotency_key_raises_integrity_error(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repo = CaptureRepository(session)
    key = "idem-key-duplicate"

    await repo.create_capture(
        user_id,
        id=uuid7(),
        raw_text="1件目",
        idempotency_key=key,
        request_hash=_HASH_A,
    )

    with pytest.raises(IntegrityError):
        await repo.create_capture(
            user_id,
            id=uuid7(),
            raw_text="2件目",
            idempotency_key=key,
            request_hash=_HASH_B,
        )
