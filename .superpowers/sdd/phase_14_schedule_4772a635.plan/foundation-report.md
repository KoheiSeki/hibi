# Hibi Milestone 1 Foundation Report

## 実施結果

Week 1-2 の基盤を `/Users/koheiseki/dev/git/hibi` の
`feat/phase14-implementation` に実装した。Next.js は UI と Supabase Auth
セッションのみを担当し、FastAPI を業務 API・認証検証・認可の境界とした。

## 主要ファイル

- ルート: `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`,
  `justfile`, `.env.example`, `docker-compose.yml`, `render.yaml`
- Web: `apps/web`（Next.js 16.3.6、React 19.3.0、TypeScript strict、
  Supabase SSR、login/logout、Vitest、ESLint）
- API: `apps/api`（Python 3.14、FastAPI、uv、Ruff、ty、pytest、
  JWT/JWKS、RFC 9457、request ID、Dockerfile）
- API 契約: `contracts/openapi.json`, `scripts/export_openapi.py`,
  `packages/api-client/openapi-ts.config.ts`,
  `packages/api-client/src/generated`
- Database: `supabase/config.toml`,
  `supabase/migrations/20260924000100_foundation.sql`,
  `supabase/tests/foundation.test.sql`
- CI: `.github/workflows/ci.yml`
- 設計資料: `docs/architecture`（承認済み Phase 14 文書一式）

## アーキテクチャ決定

1. FastAPI の OpenAPI を唯一の API 契約とし、明示的な `operationId` から
   `@hey-api/openapi-ts` で TypeScript クライアントを生成する。
2. 正常 JSON は `ApiResponse[T]` による `{data: ...}`、エラーは
   `application/problem+json` の unwrapped RFC 9457 Problem Details とする。
3. request ID を middleware で生成・伝播し、response header と
   Problem Details の `requestId` を一致させる。
4. Supabase access token は FastAPI が JWKS、issuer、audience、expiry、
   algorithm を検証し、検証済み UUID から `Principal` を生成する。
5. 所有者スコープは Principal の `user_id` を service から repository
   seam へ必ず渡す。業務層では `HTTPException` を使用しない。
6. DB 履歴は `supabase/migrations` のみとし、Alembic は導入しない。
   業務 table は private `app` schema に置き、`hibi_runtime` role にだけ
   必要な権限を付与する。
7. Browser に公開するのは Supabase publishable key のみとし、
   service-role key や DB credential は client bundle に含めない。
8. `cryptography` 50.0.1 は local ARM64 container で illegal instruction
   となったため、再現確認後に 46.0.3 へ固定した。

## TDD 記録

- Backend RED:
  `uv run --project apps/api pytest apps/api/tests`
  は実装前に `ModuleNotFoundError: No module named 'hibi'` で失敗した。
- Frontend RED:
  `corepack pnpm --filter @hibi/web test`
  は実装前に `Cannot find package '@/lib/api/request-api'` で失敗した。
- GREEN:
  Backend 7 tests、Frontend 3 tests が成功した。
- Container regression RED:
  初回 API image は editable install の参照切れ、その修正後は
  `cryptography` 50.0.1 の illegal instruction で起動失敗した。
- Container regression GREEN:
  non-editable install と `cryptography==46.0.3` に修正し、
  `{"data":{"status":"ok"}}` を確認した。

## 検証コマンドと結果

### 依存関係

- `corepack pnpm install --frozen-lockfile`
  - lockfile は最新、exit 0
- `uv sync --project apps/api --frozen --python 3.14`
  - 36 packages を確認、exit 0

### Web / TypeScript

- `corepack pnpm format:check`
  - 全対象が Prettier 準拠、exit 0
- `corepack pnpm lint`
  - API client の `tsc --noEmit` と Web ESLint が成功、exit 0
- `corepack pnpm typecheck`
  - API client と Web の strict typecheck が成功、exit 0
- `corepack pnpm test`
  - Web: 1 file / 3 tests passed、API client: no-test 設定で exit 0
- `NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=verify-placeholder corepack pnpm build`
  - Next.js 16.3.6 production build と API client build が成功、exit 0

### Python / FastAPI

- `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`
  - 15 files formatted、exit 0
- `uv run --project apps/api ruff check apps/api/src apps/api/tests scripts`
  - All checks passed、exit 0
- `uv run --project apps/api ty check apps/api/src`
  - All checks passed、exit 0
- `uv run --project apps/api pytest apps/api/tests`
  - 7 passed、exit 0
  - FastAPI TestClient から Starlette の `httpx` deprecation warning が 1 件
- `uv run --project apps/api python scripts/export_openapi.py`
  - `contracts/openapi.json` を生成、exit 0
- `corepack pnpm --filter @hibi/api-client generate`
  - 生成 client 3 files を更新、exit 0

### Container / Compose

- `docker compose build`
  - `hibi-api` と `hibi-web` の両 image を build、exit 0
- `docker compose config --quiet`
  - compose 設定検証成功、exit 0
- `docker run -d -p 18000:8000 hibi-api` と
  `curl http://localhost:18000/api/v1/health`
  - `{"data":{"status":"ok"}}`、exit 0

## 未検証事項・既知の制約

- local 環境に Supabase CLI がないため、migration の実 DB 適用と pgTAP
  (`supabase/tests/foundation.test.sql`) は未実行。
- host の port 3000 が別プロセスで使用中だったため、`docker compose up`
  による Web/API 同時起動 smoke test は未実行。両 image の build と API
  image の単独起動は成功している。
- pytest は Starlette TestClient の upstream deprecation warning を 1 件出す。
- pnpm は `unrs-resolver` の install script を承認なしで無効化した旨を警告するが、
  install、lint、typecheck、test、build は成功した。

## Commit

- `ae939dc98d8c8b5cfba7fa50cec5a87afbe233a4`
  `feat: establish Hibi application foundation`
- 本 report は後続の `docs: add foundation implementation report` commit に格納する。
