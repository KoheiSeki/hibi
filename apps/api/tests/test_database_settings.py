import pytest

from hibi.core.config import get_settings


def test_database_url_reads_hibi_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "HIBI_DATABASE_URL",
        "postgresql+asyncpg://hibi_runtime_user:secret@127.0.0.1:54322/postgres",
    )
    get_settings.cache_clear()
    try:
        assert (
            get_settings().database_url
            == "postgresql+asyncpg://hibi_runtime_user:secret@127.0.0.1:54322/postgres"
        )
    finally:
        get_settings.cache_clear()
