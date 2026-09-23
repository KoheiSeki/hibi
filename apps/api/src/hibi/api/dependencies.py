from functools import lru_cache

import httpx
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from hibi.auth.jwt_verifier import JwtVerifier, TokenVerificationError
from hibi.auth.principal import Principal
from hibi.core.config import get_settings
from hibi.core.errors import AuthenticationError

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_jwt_verifier() -> JwtVerifier:
    settings = get_settings()

    def fetch_jwks() -> dict[str, object]:
        response = httpx.get(settings.jwks_url, timeout=5.0)
        response.raise_for_status()
        return response.json()

    return JwtVerifier(
        issuer=settings.jwt_issuer,
        audience=settings.supabase_jwt_audience,
        jwks_provider=fetch_jwks,
    )


def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: JwtVerifier = Depends(get_jwt_verifier),
) -> Principal:
    if credentials is None:
        raise AuthenticationError
    try:
        return verifier.verify(credentials.credentials)
    except TokenVerificationError as error:
        raise AuthenticationError from error
