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
