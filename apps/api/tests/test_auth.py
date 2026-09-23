from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from hibi.auth.jwt_verifier import JwtVerifier, TokenVerificationError


def test_verifier_builds_principal_from_valid_jwks() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "https://project.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    verifier = JwtVerifier(
        issuer="https://project.supabase.co/auth/v1",
        audience="authenticated",
        jwks_provider=lambda: {"keys": [public_jwk]},
    )
    principal = verifier.verify(token)
    assert principal.user_id == UUID("11111111-1111-4111-8111-111111111111")


def test_verifier_rejects_wrong_issuer() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "test-key", "use": "sig", "alg": "RS256"})
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "https://evil.example",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )
    verifier = JwtVerifier(
        issuer="https://project.supabase.co/auth/v1",
        audience="authenticated",
        jwks_provider=lambda: {"keys": [public_jwk]},
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)
