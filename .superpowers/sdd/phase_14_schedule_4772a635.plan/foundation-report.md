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

---

## Foundation review 修正（CHANGES_REQUIRED 対応）

### 修正内容

1. Database role を privilege role と login role に分離した。
   `hibi_runtime` は `NOLOGIN` のまま権限だけを保持し、
   `hibi_runtime_user` は制限付き `LOGIN INHERIT` role として
   `hibi_runtime` の member にした。password は migration に保存せず、
   deployment secret から out-of-band で設定する。
2. migration を同一 clean PostgreSQL に 2 回適用できるようにした。
   role 作成、table 作成、trigger 再作成を再実行可能にし、
   runtime login と継承権限を実接続で確認する
   `scripts/verify_migration.sh` を追加した。
3. FastAPI の 401、404、422、500 response に
   `ProblemDetails` と `application/problem+json` を明示した。
   `contracts/openapi.json` と生成 TypeScript client は
   `ProblemDetails` 型の error response を持つ。
4. すべての Problem Details response に `X-Request-ID` を直接設定し、
   middleware を途中で抜ける unexpected 500 でも body の `requestId` と
   response header が一致するようにした。
5. Web API utility の fetch phase と JSON decode phase を分離した。
   fetch rejection は `network`、不正 JSON は `invalid-response`、
   abort は `aborted` になる。
6. JWKS key を既定 300 秒 TTL で process 内 cache する。
   cache hit では provider を呼ばず、未知の `kid` では cache を 1 回だけ
   強制 refresh して key rotation に対応する。cache access は lock で保護する。
7. CI に database migration verification、Docker/Compose build、
   API health smoke test を追加した。Supabase CLI 非依存の database job は
   digest 固定の PostgreSQL 17 に migration を 2 回適用し、role、trigger、
   password-authenticated runtime access を検証する。
8. exporter と formatter の競合を避けるため
   `contracts/openapi.json` を `.prettierignore` に追加し、
   OpenAPI/client 再生成が決定的であることを checksum で確認した。

### TDD RED

- Backend:
  `uv run --project apps/api pytest apps/api/tests/test_api.py apps/api/tests/test_auth.py`
  - exit 1
  - `4 failed, 7 passed`
  - unexpected 500 の `X-Request-ID` 欠落
  - OpenAPI の 500 response 欠落
  - `JwtVerifier` に cache TTL API がなく cache hit/unknown-kid refresh test が失敗
- Frontend:
  `corepack pnpm --filter @hibi/web test`
  - exit 1
  - `1 failed, 4 passed`
  - malformed JSON が `invalid-response` ではなく `network` になった
- Database:
  PostgreSQL 17 clean container に既存 migration と
  `supabase/tests/foundation.verify.sql` を適用
  - exit 3
  - `hibi_runtime_user must be an inheriting LOGIN role`

### Focused GREEN

- `uv run --project apps/api pytest apps/api/tests/test_api.py apps/api/tests/test_auth.py`
  - `11 passed, 1 warning`, exit 0
- `corepack pnpm --filter @hibi/web test`
  - `1 file / 5 tests passed`, exit 0
- `bash scripts/verify_migration.sh`
  - migration を clean DB に 2 回適用
  - runtime role membership、auth profile trigger、
    out-of-band password login、table access を確認
  - `Migration applied twice; runtime login and inherited privileges verified.`
  - exit 0

### Full verification

- `corepack pnpm install --frozen-lockfile`
  - lockfile 最新、exit 0
- `uv sync --project apps/api --frozen --python 3.14`
  - dependency sync 成功、exit 0
- `corepack pnpm format:check`
  - Prettier check 成功、exit 0
- `corepack pnpm lint`
  - ESLint と API client type lint 成功、exit 0
- `corepack pnpm typecheck`
  - Web/API client TypeScript typecheck 成功、exit 0
- `corepack pnpm test`
  - Web `5 passed`、API client no-test check 成功、exit 0
- `NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=verify-placeholder corepack pnpm build`
  - Next.js production build と API client build 成功、exit 0
- `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`
  - `16 files already formatted`、exit 0
- `uv run --project apps/api ruff check apps/api/src apps/api/tests scripts`
  - `All checks passed!`、exit 0
- `uv run --project apps/api ty check apps/api/src`
  - `All checks passed!`、exit 0
- `uv run --project apps/api pytest apps/api/tests`
  - `11 passed, 1 warning`、exit 0
- OpenAPI/client deterministic regeneration
  - exporter と generator を再実行し before/after checksum が一致
  - checksum:
    `2c4287a8786d9f84684fe2cde8aec71c4accccd7`
  - exit 0
- `docker compose build`
  - `hibi-api`、`hibi-web` build 成功、exit 0
- API image smoke test:
  `docker run --detach --publish 18000:8000 hibi-api` と health request
  - `{"data":{"status":"ok"}}`
  - exit 0
- IDE diagnostics:
  - API/Web とも linter error なし

### 既知の注意点

- local 環境には Supabase CLI がないため pgTAP 自体は未実行。
  同じ migration と重要な role/trigger/access assertion は
  pinned PostgreSQL container の SQL verification で実行し、CI にも追加した。
- pytest には FastAPI TestClient 経由の upstream
  `StarletteDeprecationWarning` が 1 件残る。
- pnpm は `unrs-resolver` の install script を未承認として無効化する警告を出すが、
  lint、typecheck、test、build はすべて成功している。

### 修正 commit

- `4195c05f901ec9c1081e28a031d7dae7f545f764`
  `fix: address foundation review findings`
- 本追記は後続の `docs: append foundation review fix report` commit に格納する。
