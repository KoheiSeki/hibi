import os
from pathlib import Path

import httpx

from hibi.core.config import Settings, get_settings

_API_ROOT = Path(__file__).resolve().parents[2]
ME_PATH = "/api/v1/me"


def load_hibi_env_from_api_dotenv() -> None:
    """Load HIBI_* from `.env.local`, then fill missing values from `.env`."""
    for env_path in (_API_ROOT / ".env.local", _API_ROOT / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key.startswith("HIBI_") or key in os.environ:
                continue
            os.environ[key] = value.strip().strip('"').strip("'")


def supabase_local_reachable(settings: Settings | None = None) -> bool:
    resolved = settings or get_settings()
    base = resolved.supabase_url.rstrip("/")
    if "127.0.0.1" not in base and "localhost" not in base:
        return False
    try:
        response = httpx.get(resolved.jwks_url, timeout=3.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def integration_auth_config() -> tuple[str, str, str] | None:
    email = os.environ.get("HIBI_TEST_USER_EMAIL")
    password = os.environ.get("HIBI_TEST_USER_PASSWORD")
    publishable_key = os.environ.get("HIBI_SUPABASE_PUBLISHABLE_KEY")
    if not email or not password or not publishable_key:
        return None
    return email, password, publishable_key


def sign_in_with_password(
    *,
    email: str,
    password: str,
    publishable_key: str,
    settings: Settings | None = None,
) -> tuple[str, str]:
    resolved = settings or get_settings()
    url = f"{resolved.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": publishable_key,
        "Authorization": f"Bearer {publishable_key}",
        "Content-Type": "application/json",
    }
    response = httpx.post(
        url,
        headers=headers,
        json={"email": email, "password": password},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    access_token = payload.get("access_token")
    user = payload.get("user") or {}
    user_id = user.get("id")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Supabase auth response did not include access_token")
    if not isinstance(user_id, str) or not user_id:
        raise RuntimeError("Supabase auth response did not include user.id")
    return access_token, user_id


def tamper_access_token(token: str) -> str:
    if not token:
        return token
    last = token[-1]
    replacement = "a" if last != "a" else "b"
    return f"{token[:-1]}{replacement}"
