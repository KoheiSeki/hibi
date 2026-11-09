set shell := ["bash", "-cu"]

install:
    corepack pnpm install --frozen-lockfile
    uv sync --project apps/api --frozen --python 3.14

dev-api:
    cd apps/api && uv run uvicorn hibi.api.main:app --reload --port 8000

dev-worker:
    cd apps/api && uv run arq hibi.jobs.main.WorkerSettings

dev-web:
    corepack pnpm dev:web

openapi:
    uv run --project apps/api python scripts/export_openapi.py
    corepack pnpm openapi:client

check:
    corepack pnpm format:check
    corepack pnpm lint
    corepack pnpm typecheck
    corepack pnpm test
    corepack pnpm build
    uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
    uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
    uv run --project apps/api ty check apps/api/src
    uv run --project apps/api pytest apps/api/tests
