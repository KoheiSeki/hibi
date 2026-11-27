from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

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
        allowed_algorithms=frozenset({"RS256"}),
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
        allowed_algorithms=frozenset({"RS256"}),
        jwks_provider=lambda: {"keys": [public_jwk]},
    )
    with pytest.raises(TokenVerificationError):
        verifier.verify(token)


def test_verifier_reuses_jwks_within_cache_ttl() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key(), as_dict=True)
    public_jwk.update({"kid": "cached-key", "use": "sig", "alg": "RS256"})
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "https://project.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "cached-key"},
    )
    fetch_count = 0

    def provide_jwks() -> dict[str, object]:
        nonlocal fetch_count
        fetch_count += 1
        return {"keys": [public_jwk]}

    verifier = JwtVerifier(
        issuer="https://project.supabase.co/auth/v1",
        audience="authenticated",
        allowed_algorithms=frozenset({"RS256"}),
        jwks_provider=provide_jwks,
        cache_ttl_seconds=300,
    )

    verifier.verify(token)
    verifier.verify(token)

    assert fetch_count == 1


def test_verifier_refreshes_jwks_once_for_unknown_kid() -> None:
    old_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old_public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(old_private_key.public_key(), as_dict=True)
    old_public_jwk.update({"kid": "old-key", "use": "sig", "alg": "RS256"})
    new_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(new_private_key.public_key(), as_dict=True)
    new_public_jwk.update({"kid": "new-key", "use": "sig", "alg": "RS256"})
    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "https://project.supabase.co/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        new_private_key,
        algorithm="RS256",
        headers={"kid": "new-key"},
    )
    responses = iter(({"keys": [old_public_jwk]}, {"keys": [new_public_jwk]}))
    fetch_count = 0

    def provide_jwks() -> dict[str, object]:
        nonlocal fetch_count
        fetch_count += 1
        return next(responses)

    verifier = JwtVerifier(
        issuer="https://project.supabase.co/auth/v1",
        audience="authenticated",
        allowed_algorithms=frozenset({"RS256"}),
        jwks_provider=provide_jwks,
        cache_ttl_seconds=300,
    )

    principal = verifier.verify(token)

    assert principal.user_id == UUID("11111111-1111-4111-8111-111111111111")
    assert fetch_count == 2


def test_verifier_accepts_allowed_es256_token() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(
        private_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"kid": "es256-key", "use": "sig", "alg": "ES256"})

    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "http://127.0.0.1:54321/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "es256-key"},
    )

    verifier = JwtVerifier(
        issuer="http://127.0.0.1:54321/auth/v1",
        audience="authenticated",
        allowed_algorithms=frozenset({"ES256"}),
        jwks_provider=lambda: {"keys": [public_jwk]},
    )

    principal = verifier.verify(token)

    assert principal.user_id == UUID("11111111-1111-4111-8111-111111111111")


def test_verifier_rejects_algorithm_outside_allowlist() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = jwt.algorithms.ECAlgorithm.to_jwk(
        private_key.public_key(),
        as_dict=True,
    )
    public_jwk.update({"kid": "es256-key", "use": "sig", "alg": "ES256"})

    token = jwt.encode(
        {
            "sub": "11111111-1111-4111-8111-111111111111",
            "iss": "http://127.0.0.1:54321/auth/v1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        private_key,
        algorithm="ES256",
        headers={"kid": "es256-key"},
    )

    verifier = JwtVerifier(
        issuer="http://127.0.0.1:54321/auth/v1",
        audience="authenticated",
        allowed_algorithms=frozenset({"RS256"}),
        jwks_provider=lambda: {"keys": [public_jwk]},
    )

    with pytest.raises(TokenVerificationError):
        verifier.verify(token)
