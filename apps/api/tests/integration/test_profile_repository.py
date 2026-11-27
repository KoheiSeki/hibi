from collections.abc import AsyncGenerator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine, get_engine
from hibi.modules.profiles.repository import ProfileRepository


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


@pytest.mark.integration
async def test_get_timezone_defaults_to_tokyo_and_follows_the_profile(
    session: AsyncSession,
) -> None:
    user_id = uuid4()
    await _insert_auth_user(session, user_id)
    repository = ProfileRepository(session)

    assert await repository.get_timezone(user_id) == "Asia/Tokyo"

    await session.execute(
        text("UPDATE app.profiles SET timezone = :timezone WHERE user_id = :user_id"),
        {"timezone": "America/New_York", "user_id": user_id},
    )

    assert await repository.get_timezone(user_id) == "America/New_York"


@pytest.mark.integration
async def test_get_timezone_falls_back_to_utc_without_a_profile(
    session: AsyncSession,
) -> None:
    repository = ProfileRepository(session)

    assert await repository.get_timezone(uuid4()) == "UTC"
