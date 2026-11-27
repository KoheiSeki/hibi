import pytest
from auth_contract_helpers import assert_unauthorized_problem
from fastapi.testclient import TestClient
from supabase_local_helpers import (
    ME_PATH,
    sign_in_with_password,
    tamper_access_token,
)

from hibi.api.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def integration_client() -> TestClient:
    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture(scope="module")
def supabase_session(
    require_supabase_local_integration: tuple[str, str, str],
) -> tuple[str, str]:
    email, password, publishable_key = require_supabase_local_integration
    access_token, user_id = sign_in_with_password(
        email=email,
        password=password,
        publishable_key=publishable_key,
    )
    return access_token, user_id


def test_me_accepts_supabase_local_access_token(
    integration_client: TestClient,
    supabase_session: tuple[str, str],
) -> None:
    access_token, user_id = supabase_session
    response = integration_client.get(
        ME_PATH,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"data": {"userId": user_id}}


def test_me_rejects_tampered_supabase_token(
    integration_client: TestClient,
    supabase_session: tuple[str, str],
) -> None:
    access_token, _ = supabase_session
    tampered = tamper_access_token(access_token)
    response = integration_client.get(
        ME_PATH,
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert_unauthorized_problem(response)


def test_me_rejects_missing_authorization_with_real_jwks(
    integration_client: TestClient,
) -> None:
    response = integration_client.get(ME_PATH)
    assert_unauthorized_problem(response)
