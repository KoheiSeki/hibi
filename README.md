# Hibi

Hibi is an everyday copilot built as a modular monolith. Next.js owns UI and the Supabase Auth session; FastAPI owns business logic, authorization, and data access.

## Requirements

- Node.js 22+ and pnpm 10.17.1
- Python 3.14 and uv
- Docker (optional)
- Supabase CLI (for database migrations)

## Local development

```sh
cp .env.example .env
corepack pnpm install --frozen-lockfile
uv sync --project apps/api --frozen --python 3.14
docker compose up --build
```

Or run `pnpm dev:web` and `uv run --project apps/api uvicorn hibi.api.main:app --reload --port 8000` separately. See `docs/architecture` for the approved system design.

## Database roles and migrations

`hibi_runtime` is a `NOLOGIN` privilege role. The application connects as
`hibi_runtime_user`, a constrained `LOGIN` role that inherits
`hibi_runtime`. The migration intentionally never stores a password; provision
one through the deployment secret channel:

```sql
alter role hibi_runtime_user password 'value-from-your-secret-store';
```

Set that value only in `HIBI_DATABASE_URL`. To apply the foundation migration
twice on a clean PostgreSQL 17 container, verify role inheritance, and test a
password-authenticated runtime connection:

```sh
bash scripts/verify_migration.sh
```

Supabase CLI users can additionally run `supabase db reset` and
`supabase test db` for the pgTAP suite. CI always runs the pinned PostgreSQL
equivalent above, so role and migration checks do not depend on a locally
installed Supabase CLI.
