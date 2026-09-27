#!/usr/bin/env bash
set -euo pipefail

# 1. apps/api/.env.local を読み込む
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT}/apps/api/.env.local"

# envファイルが存在しない場合
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

# 2. 必須変数チェック: HIBI_SUPABASE_URL, HIBI_SUPABASE_PUBLISHABLE_KEY,
#    HIBI_TEST_USER_EMAIL, HIBI_TEST_USER_PASSWORD, HIBI_API_BASE_URL
required=(
    HIBI_SUPABASE_URL
    HIBI_SUPABASE_PUBLISHABLE_KEY
    HIBI_TEST_USER_EMAIL
    HIBI_TEST_USER_PASSWORD
    HIBI_API_BASE_URL
)

missing=()
for name in "${required[@]}"; do
    if ! declare -p "${name}" >/dev/null 2>&1 || [[ -z "${!name}" ]]; then
        missing+=("$name")
    fi
done

if ((${#missing[@]} > 0)); then
    echo "Required variables unset or empty: ${missing[*]}" >&2
    echo "Set them in ${ENV_FILE} (see apps/api/.env.example)." >&2
    exit 1
fi

for command in curl jq; do
    if ! command -v "${command}" >/dev/null 2>&1; then
        echo "Required command not found: ${command}" >&2
        exit 1
    fi
done

# 3. Supabase Local の JWKS endpoint に到達できることを確認
curl -sfS "${HIBI_SUPABASE_URL%/}/auth/v1/.well-known/jwks.json" >/dev/null

# 4. curl POST .../auth/v1/token?grant_type=password → jq -r .access_token, .user.id
auth_request="$(
  jq -n \
    --arg email "${HIBI_TEST_USER_EMAIL}" \
    --arg password "${HIBI_TEST_USER_PASSWORD}" \
    '{email: $email, password: $password}'
)"
auth_response="$(curl -sfS -X POST \
  "${HIBI_SUPABASE_URL%/}/auth/v1/token?grant_type=password" \
  -H "apikey: ${HIBI_SUPABASE_PUBLISHABLE_KEY}" \
  -H "Authorization: Bearer ${HIBI_SUPABASE_PUBLISHABLE_KEY}" \
  -H "Content-Type: application/json" \
  -d "${auth_request}")"
access_token="$(jq -er '.access_token' <<<"${auth_response}")"
user_id="$(jq -er '.user.id' <<<"${auth_response}")"

# 5. curl -sf -H "Authorization: Bearer $token" "$HIBI_API_BASE_URL/api/v1/me"
#    → jq -e '.data.userId == env.EXPECTED_UID'
me_response="$(curl -sf \
  -H "Authorization: Bearer ${access_token}" \
  "${HIBI_API_BASE_URL%/}/api/v1/me")"
jq -e --arg uid "${user_id}" '.data.userId == $uid' <<<"${me_response}" >/dev/null

# 6. 改ざん token で curl → HTTP 401 + Content-Type problem+json（任意）
tampered="${access_token:0:${#access_token}-1}"
last="${access_token: -1}"
[[ "${last}" == "a" ]] && tampered+="b" || tampered+="a"

status="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${tampered}" \
  "${HIBI_API_BASE_URL%/}/api/v1/me")"
[[ "${status}" == "401" ]] || { echo "expected 401, got ${status}" >&2; exit 1; }

echo "Week 2 auth slice verification passed."
