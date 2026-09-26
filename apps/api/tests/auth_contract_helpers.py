from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from hibi.api.dependencies import get_jwt_verifier
from hibi.api.main import create_app
from hibi.auth.jwt_verifier import JwtVerifier, JwksProvider

TEST_ISSUER = "http://127.0.0.1:54321/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_USER_ID = UUID("11111111-1111-4111-8111-111111111111")
TEST_KID = "contract-test-es256"


def build_es256_jwk(private_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(
        private_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"kid": TEST_KID, "use": "sig", "alg": "ES256"})
    return public_jwk


def encode_access_token(
    private_key: ec.EllipticCurvePrivateKey,
    *,
    sub: str = str(TEST_USER_ID),
    iss: str = TEST_ISSUER,
    aud: str = TEST_AUDIENCE,
    exp: datetime | None = None,
    algorithm: str = "ES256",
    kid: str = TEST_KID,
) -> str:
    expires_at = exp if exp is not None else datetime.now(UTC) + timedelta(minutes=5)
    return jwt.encode(
        {
            "sub": sub,
            "iss": iss,
            "aud": aud,
            "exp": expires_at,
        },
        private_key,
        algorithm=algorithm,
        headers={"kid": kid},
    )


def create_auth_contract_client(
    *,
    jwks_provider: JwksProvider | None = None,
    allowed_algorithms: frozenset[str] = frozenset({"ES256"}),
) -> tuple[TestClient, ec.EllipticCurvePrivateKey, dict[str, str]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = build_es256_jwk(private_key)
    provider = jwks_provider or (lambda: {"keys": [public_jwk]})
    verifier = JwtVerifier(
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        allowed_algorithms=allowed_algorithms,
        jwks_provider=provider,
        cache_ttl_seconds=300,
    )
    app = create_app()
    app.dependency_overrides[get_jwt_verifier] = lambda: verifier
    client = TestClient(app, raise_server_exceptions=False)
    return client, private_key, public_jwk


def assert_unauthorized_problem(response) -> dict[str, object]:
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401
    assert body["type"] == "https://api.hibi.example/problems/unauthorized"
    assert body["title"] == "Unauthorized"
    assert body["requestId"] == response.headers["x-request-id"]
    assert "instance" in body
    serialized = response.text.lower()
    assert "bearer" not in serialized
    assert "eyj" not in serialized
    return body
