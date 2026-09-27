from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.core.config import get_settings
from hibi.db.engine import dispose_engine
from hibi.db.session import get_session


def _database_url() -> str:
    return get_settings().database_url


async def _open_session() -> tuple[AsyncGenerator[AsyncSession], AsyncSession]:
    if not _database_url():
        pytest.skip("HIBI_DATABASE_URL is not configured")
    agen = get_session()
    try:
        session = await agen.__anext__()
    except OperationalError:
        await agen.aclose()
        pytest.skip("PostgreSQL is not reachable at HIBI_DATABASE_URL")
    return agen, session


@pytest.mark.integration
async def test_get_session_selects_one() -> None:
    agen, session = await _open_session()
    try:
        assert await session.scalar(text("SELECT 1")) == 1
    finally:
        await agen.aclose()
        await dispose_engine()


@pytest.mark.integration
async def test_runtime_role_can_select_captures() -> None:
    agen, session = await _open_session()
    try:
        count = await session.scalar(text("SELECT count(*) FROM app.captures"))
        assert count is not None
        assert count >= 0
    finally:
        await agen.aclose()
        await dispose_engine()
