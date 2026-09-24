from collections.abc import Callable
from threading import Lock
from time import monotonic
from typing import Any
from uuid import UUID

import jwt

from hibi.auth.principal import Principal

JwksProvider = Callable[[], dict[str, Any]]
Clock = Callable[[], float]


class TokenVerificationError(Exception):
    pass


class JwtVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        allowed_algorithms: frozenset[str],
        jwks_provider: JwksProvider,
        cache_ttl_seconds: float = 300,
        clock: Clock = monotonic,
    ) -> None:
        if cache_ttl_seconds <= 0:
            raise ValueError("cache_ttl_seconds must be positive")
        if not allowed_algorithms:
            raise ValueError("allowed_algorithms must not be empty")

        self._issuer = issuer
        self._audience = audience
        self._allowed_algorithms = allowed_algorithms
        self._jwks_provider = jwks_provider
        self._cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock
        self._cached_keys: tuple[dict[str, Any], ...] = ()
        self._cache_expires_at = 0.0
        self._cache_lock = Lock()

    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            jwk = self._find_key(kid, self._get_keys())
            if jwk is None:
                jwk = self._find_key(kid, self._get_keys(force_refresh=True))
            if jwk is None:
                raise TokenVerificationError("token signing key not found")

            header_algorithms = header.get("alg")
            jwk_algorithms = jwk.get("alg")

            if (
                not isinstance(header_algorithms, str)
                or not isinstance(jwk_algorithms, str)
                or header_algorithms != jwk_algorithms
                or header_algorithms not in self._allowed_algorithms
            ):
                raise TokenVerificationError("token algorithm is not allowed")

            public_key = jwt.PyJWK.from_dict(jwk).key
            claims = jwt.decode(
                token,
                public_key,
                algorithms=[header_algorithms],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["sub", "iss", "aud", "exp"]},
            )
            return Principal(user_id=UUID(claims["sub"]), permissions=frozenset())
        except TokenVerificationError:
            raise
        except (KeyError, ValueError, jwt.PyJWTError) as error:
            raise TokenVerificationError("token verification failed") from error

    def _get_keys(self, *, force_refresh: bool = False) -> tuple[dict[str, Any], ...]:
        with self._cache_lock:
            now = self._clock()
            if not force_refresh and self._cached_keys and now < self._cache_expires_at:
                return self._cached_keys

            jwks = self._jwks_provider()
            keys = jwks.get("keys")
            if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
                raise TokenVerificationError("invalid JWKS response")
            self._cached_keys = tuple(keys)
            self._cache_expires_at = now + self._cache_ttl_seconds
            return self._cached_keys

    @staticmethod
    def _find_key(kid: object, keys: tuple[dict[str, Any], ...]) -> dict[str, Any] | None:
        return next((key for key in keys if key.get("kid") == kid), None)
