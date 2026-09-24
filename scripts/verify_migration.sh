#!/usr/bin/env bash
set -euo pipefail

POSTGRES_IMAGE="${POSTGRES_IMAGE:-postgres:17@sha256:f4c66b820c6f974249089d3d16d86a3698eae11e8746eb6644b2271031e91232}"
container="hibi-migration-test-$$"

cleanup() {
  docker rm -f "${container}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run --detach --name "${container}" \
  --env POSTGRES_PASSWORD=postgres \
  "${POSTGRES_IMAGE}" >/dev/null

for _attempt in {1..30}; do
  if docker exec "${container}" pg_isready --username postgres >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "${container}" pg_isready --username postgres >/dev/null

docker exec --interactive "${container}" psql --set ON_ERROR_STOP=1 --username postgres <<'SQL'
create role anon;
create role authenticated;
create schema auth;
create table auth.users (id uuid primary key);
SQL

docker cp supabase/roles.sql \
  "${container}:/roles.sql" >/dev/null
docker cp supabase/migrations/20260924000100_foundation.sql \
  "${container}:/migration.sql" >/dev/null
docker cp supabase/tests/foundation.verify.sql \
  "${container}:/verify.sql" >/dev/null

# Apply roles twice to verify idempotency.
docker exec "${container}" psql \
  --set ON_ERROR_STOP=1 \
  --username postgres \
  --file /roles.sql
docker exec "${container}" psql \
  --set ON_ERROR_STOP=1 \
  --username postgres \
  --file /roles.sql
# Apply migration twice to verify idempotency.
docker exec "${container}" psql \
  --set ON_ERROR_STOP=1 \
  --username postgres \
  --file /migration.sql
docker exec "${container}" psql \
  --set ON_ERROR_STOP=1 \
  --username postgres \
  --file /migration.sql
docker exec "${container}" psql \
  --set ON_ERROR_STOP=1 \
  --username postgres \
  --file /verify.sql

# The password is intentionally provisioned outside the migration.
docker exec "${container}" psql --set ON_ERROR_STOP=1 --username postgres \
  --command "alter role hibi_runtime_user password 'local-runtime-password';"
docker exec --env PGPASSWORD=local-runtime-password "${container}" \
  psql --set ON_ERROR_STOP=1 --host 127.0.0.1 --username hibi_runtime_user \
  --dbname postgres --command "select count(*) from app.profiles;" >/dev/null

echo "Migration applied twice; runtime login and inherited privileges verified."
