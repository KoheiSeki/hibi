from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from hibi.core.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        database_url = get_settings().database_url
        if not database_url:
            raise RuntimeError("HIBI_DATABASE_URL is not configured.")
        _engine = create_async_engine(
            database_url,
            echo=False,
            pool_size=2,
            max_overflow=3,
        )
    return _engine


async def dispose_engine() -> None:
    global _engine
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None
