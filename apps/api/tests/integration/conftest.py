import pytest
from supabase_local_helpers import (
    integration_auth_config,
    load_hibi_env_from_api_dotenv,
    supabase_local_reachable,
)

from hibi.api.dependencies import get_jwt_verifier
from hibi.core.config import get_settings


@pytest.fixture(scope="session", autouse=True)
def _load_api_env_for_integration() -> None:
    load_hibi_env_from_api_dotenv()
    get_settings.cache_clear()
    get_jwt_verifier.cache_clear()


@pytest.fixture(scope="module")
def require_supabase_local_integration() -> tuple[str, str, str]:
    if not supabase_local_reachable():
        pytest.skip("Supabase local is not reachable at HIBI_SUPABASE_URL (JWKS)")
    auth = integration_auth_config()
    if auth is None:
        pytest.skip(
            "Set HIBI_TEST_USER_EMAIL, HIBI_TEST_USER_PASSWORD, "
            "and HIBI_SUPABASE_PUBLISHABLE_KEY in apps/api/.env.local"
        )
    return auth
