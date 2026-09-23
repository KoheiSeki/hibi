from collections.abc import Callable
from typing import Any
from uuid import UUID

import jwt

from hibi.auth.principal import Principal

JwksProvider = Callable[[], dict[str, Any]]


class TokenVerificationError(Exception):
    pass


class JwtVerifier:
    def __init__(self, *, issuer: str, audience: str, jwks_provider: JwksProvider) -> None:
        self._issuer = issuer
        self._audience = audience
        self._jwks_provider = jwks_provider

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            jwk = next(key for key in self._jwks_provider()["keys"] if key.get("kid") == kid)
            public_key = jwt.PyJWK.from_dict(jwk).key
            claims = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
            return Principal(user_id=UUID(claims["sub"]), permissions=frozenset())
        except (KeyError, StopIteration, ValueError, jwt.PyJWTError) as error:
            raise TokenVerificationError("token verification failed") from error
