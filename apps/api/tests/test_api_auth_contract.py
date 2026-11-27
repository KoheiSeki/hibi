from datetime import UTC, datetime, timedelta

import jwt
from auth_contract_helpers import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_USER_ID,
    assert_unauthorized_problem,
    create_auth_contract_client,
    encode_access_token,
)
from cryptography.hazmat.primitives.asymmetric import rsa

ME_PATH = "/api/v1/me"


def test_me_rejects_missing_authorization_header() -> None:
    client, _, _ = create_auth_contract_client()
    response = client.get(ME_PATH)
    assert_unauthorized_problem(response)


def test_me_rejects_non_bearer_authorization_scheme() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(private_key)
    response = client.get(ME_PATH, headers={"Authorization": f"Token {token}"})
    assert_unauthorized_problem(response)


def test_me_rejects_expired_access_token() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(
        private_key,
        exp=datetime.now(UTC) - timedelta(minutes=1),
    )
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})
    assert_unauthorized_problem(response)


def test_me_rejects_wrong_issuer() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(private_key, iss="https://evil.example/auth/v1")
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})
    assert_unauthorized_problem(response)


def test_me_rejects_wrong_audience() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(private_key, aud="service_role")
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})
    assert_unauthorized_problem(response)


def test_me_rejects_algorithm_outside_allowlist() -> None:
    rsa_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(
        rsa_private.public_key(),
        as_dict=True,
    )
    rsa_public_jwk.update({"kid": "rsa-key", "use": "sig", "alg": "RS256"})
    client, _, _ = create_auth_contract_client(
        jwks_provider=lambda: {"keys": [rsa_public_jwk]},
        allowed_algorithms=frozenset({"ES256"}),
    )
    token = jwt.encode(
        {
            "sub": str(TEST_USER_ID),
            "iss": TEST_ISSUER,
            "aud": TEST_AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        rsa_private,
        algorithm="RS256",
        headers={"kid": "rsa-key"},
    )
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})
    assert_unauthorized_problem(response)


def test_me_rejects_tampered_signature() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(private_key)
    tampered = f"{token[:-1]}{'a' if token[-1] != 'a' else 'b'}"
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {tampered}"})
    assert_unauthorized_problem(response)


def test_me_accepts_valid_contract_token() -> None:
    client, private_key, _ = create_auth_contract_client()
    token = encode_access_token(private_key)
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"data": {"userId": str(TEST_USER_ID)}}


def failing_jwks_provider() -> dict[str, object]:
    raise ConnectionError("jwks unavailable")


def test_jwks_provider_failure_returns_500_not_401() -> None:
    client, private_key, _ = create_auth_contract_client(
        jwks_provider=failing_jwks_provider,
    )
    token = encode_access_token(private_key)
    response = client.get(ME_PATH, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 500
    assert body["type"] == "https://api.hibi.example/problems/internal-error"
    assert body["requestId"] == response.headers["x-request-id"]
    assert body["detail"] == "An unexpected error occurred."
    assert "jwks" not in response.text.lower()
