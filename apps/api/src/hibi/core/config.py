from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HIBI_", env_file=(".env", ".env.local"), extra="ignore"
    )

    supabase_url: str = "https://example.supabase.co"
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_algorithms: str = "ES256"
    cors_origins: str = "http://localhost:3000"

    database_url: str = ""

    redis_url: str = "redis://localhost:6379/0"

    jev_api_key: str = ""

    @property
    def allowed_jwt_algorithms(self) -> frozenset[str]:
        algorithms = frozenset(
            value.strip()
            for value in self.supabase_jwt_algorithms.split(",")
            if value.strip()
        )
        if not algorithms:
            raise ValueError("HIBI_SUPABASE_JWT_ALGORITHMS must not be empty")
        return algorithms

    @property
    def jwt_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.jwt_issuer}/.well-known/jwks.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
