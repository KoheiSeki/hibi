# Week 2 Step 5: Supabase Local 認証縦切り

Step 4（固定 JWKS の契約テスト）に加え、**Supabase Local が発行する実 JWT** と **実 JWKS 取得**で FastAPI が動くことを確認する。Web はブラウザでの手動チェック（Week 2 最小）または Playwright（任意）。

## 前提

- `supabase start` が動いている（JWKS: `http://127.0.0.1:54321/auth/v1/.well-known/jwks.json`）
- Auth にテストユーザーが存在する（Studio → Authentication → Users、または Auth API）。seed では作らない
- Web の proxy / session 更新が有効（Step 4 本文 §4）。ログイン直後に Server Component で session が欠けないこと

## 環境変数（API integration）

`apps/api/.env.local` に追記（値は `supabase status` 参照）。同じ変数が
`apps/api/.env` にもある場合は `.env.local` を優先する:

| 変数 | 例 / 取得元 |
|------|-------------|
| `HIBI_SUPABASE_URL` | `http://127.0.0.1:54321` |
| `HIBI_SUPABASE_PUBLISHABLE_KEY` | Publishable（anon）キー |
| `HIBI_TEST_USER_EMAIL` | テストユーザのメール |
| `HIBI_TEST_USER_PASSWORD` | テストユーザのパスワード |

Web（`.env` / `apps/web/.env.local`）は開発時どおり `NEXT_PUBLIC_SUPABASE_*` と `HIBI_API_BASE_URL=http://127.0.0.1:8000` を揃える。

## API integration テスト（Step 5）

リポジトリルートまたは `apps/api` から:

```sh
uv run --project apps/api pytest apps/api/tests/integration -m integration -v
```

CI の通常 `pytest` は `-m 'not integration'` のため **integration は実行されない**。

### テストが行うこと

1. GoTrue password login → 実 `access_token`
2. オーバーライドなしの `create_app()` + TestClient で `GET /api/v1/me` → **200**、`userId` が Auth の user id と一致
3. token 改ざん → **401 Problem**（Step 4 と同形状、`assert_unauthorized_problem`）
4. Authorization なし → **401 Problem**

Supabase 未起動・env 不足のときは **skip**（失敗ではない）。

## 手動 Web チェック（Week 2 完了の最小）

1. API: `uv run --project apps/api uvicorn hibi.api.main:app --reload --port 8000`（`apps/api/.env.local` の値を環境へ読み込んで起動）
2. Web: `pnpm dev:web`
3. ブラウザで `http://localhost:3000/login` → テストユーザーでログイン
4. `/account` に遷移すること
5. 画面に **Supabase 側の email**（`getUser()`）が表示されること
6. `/account` に **Supabase user ID** と **API user ID** の 2 行が表示され、**両方が同じ UUID** であること（`apps/web/src/app/account/page.tsx`）

失敗時の切り分け:

| 症状 | 確認 |
|------|------|
| ログイン後すぐ `/login` に戻る | Web proxy / Cookie、`NEXT_PUBLIC_SUPABASE_*` |
| account は開くが API エラー | `HIBI_API_BASE_URL`、`HIBI_SUPABASE_URL`（API が 127.0.0.1 JWKS に届くか） |
| 401 Problem が account に表示 | token と API の issuer/audience 設定の不一致 |

## 関連

- [Week 2 認証失敗契約（Step 4）](../architecture/12-week2-auth-failure-contract.md)
- [テスト・品質管理](../architecture/08-testing-quality.md)
