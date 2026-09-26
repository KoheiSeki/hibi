# Week 2 Step 4: 認証失敗の契約

## 目的

Step 3 で「ログイン → Bearer → `GET /api/v1/me` → user ID 一致」の正常系を確認したあと、Step 4 では **異常系を HTTP / OpenAPI 契約として固定**する。

- 利用者の token が無効なときは **401 + RFC 9457 Problem Details**
- **JWKS 取得などサーバー側インフラ障害**は **401 に見せない**
- Web は API の 401 を `**ApiResult` / 表示文言**として一貫して扱う

正常系だけ通る状態から、「何を信用しないか」を CI で守る段階である。

## HTTP 契約（FastAPI）

### 認証失敗（401）


| 項目           | 期待                                                  |
| ------------ | --------------------------------------------------- |
| Status       | `401`                                               |
| Content-Type | `application/problem+json`                          |
| `type`       | `https://api.hibi.example/problems/unauthorized`    |
| `title`      | `Unauthorized`                                      |
| `status`     | `401`（body と一致）                                     |
| `detail`     | 固定文言（`Authentication is required.` 等）。例外メッセージの直出し禁止 |
| `requestId`  | レスポンスヘッダ `X-Request-ID` と一致                         |
| `instance`   | リクエスト path（例: `/api/v1/me`）                         |


レスポンス body / log に **raw token、JWT payload、内部スタック、JWKS URL** を含めない。

### インフラ障害（現状: 500）

JWKS provider が未処理例外（例: `ConnectionError`）を投げた場合:


| 項目       | 期待（現状のテスト固定）                                       |
| -------- | -------------------------------------------------- |
| Status   | `500`                                              |
| `type`   | `https://api.hibi.example/problems/internal-error` |
| `detail` | `An unexpected error occurred.`（固定）                |


**MUST NOT:** 利用者の token 不正と混同して **401** を返す。

将来 503 や専用 `type` に変更する場合は、契約テストの期待値を **意図的に更新**し、ADR または本ドキュメントに理由を残す。

## 検証する認証失敗ケース（API）

`GET /api/v1/me` を対象に、TestClient + テスト用 `JwtVerifier`（固定 JWKS）で検証する。


| ケース                                        | 期待                                    |
| ------------------------------------------ | ------------------------------------- |
| Authorization ヘッダなし                        | 401                                   |
| Bearer 以外の scheme                          | 401                                   |
| 期限切れ token                                 | 401                                   |
| `iss` 不一致                                  | 401                                   |
| `aud` 不一致                                  | 401                                   |
| 許可外 algorithm（例: RS256 token / ES256 のみ許可） | 401                                   |
| 署名改ざん                                      | 401                                   |
| 有効 token（契約テスト用 ES256）                     | 200 + `{ "data": { "userId": "…" } }` |
| JWKS provider 障害                           | **500**（401 ではない）                     |


テスト用 issuer / audience は Local Supabase に合わせ `**http://127.0.0.1:54321/auth/v1**` / `**authenticated**` / **ES256** を使用する（本番 Cloud とは issuer が異なる点に注意。Verifier は設定の `HIBI_SUPABASE_URL` に従う）。

## Web 契約（契約の消費者）

### `ApiResult` への変換


| 発生源                                 | `ApiClientError.kind`    | 画面向けタイトル（`presentApiClientError`） |
| ----------------------------------- | ------------------------ | --------------------------------- |
| session に access token なし（helper 内） | `unauthenticated`        | ログインが必要です                         |
| API が 401 Problem Details           | `problem`（`status: 401`） | 認証に失敗しました                         |
| API が 500 internal-error            | `problem`（`status: 500`） | Problem の `title` をそのまま利用         |


**SHOULD:** API の 401 Problem を Web 側の `unauthenticated` と同一視しない（再ログインが必要なケースと、インフラ / 設定障害を区別するため）。

### アカウント画面（推奨ルーティング）

1. `supabase.auth.getUser()` で未ログイン → `/login` へ redirect
2. `getCurrentUserFromApi()` が `unauthenticated` → `/login` へ redirect
3. その他の API 失敗（401 Problem 含む）→ `**ApiErrorMessage` を表示**（redirect しない）

401 Problem 時も `/login` へ飛ばす UX に変更する場合は、本契約と Web テストを **セットで更新**する。

## テスト資産

### API


| ファイル                                       | 役割                                                          |
| ------------------------------------------ | ----------------------------------------------------------- |
| `apps/api/tests/auth_contract_helpers.py`  | ES256 token 生成、`assert_unauthorized_problem`、契約用 TestClient |
| `apps/api/tests/test_api_auth_contract.py` | 上表の HTTP 契約テスト                                              |
| `apps/api/tests/test_api.py`               | トークンなし 401（既存）、OpenAPI 401 メディアタイプ                          |
| `apps/api/tests/test_auth.py`              | `JwtVerifier` 単体（issuer / algorithm / ES256 等）              |


実行:

```sh
cd apps/api
uv run pytest tests/test_api_auth_contract.py -v
```

### Web


| ファイル                                               | 役割                                                                  |
| -------------------------------------------------- | ------------------------------------------------------------------- |
| `apps/web/tests/auth-failure-contract.test.ts`     | 401 Problem / unauthenticated / 500 の表示と `normalizeGeneratedResult` |
| `apps/web/tests/get-current-user-from-api.test.ts` | helper + 401 Problem マッピング                                          |
| `apps/web/tests/client-error-message.test.ts`      | `presentApiClientError`                                             |


実行:

```sh
cd apps/web
pnpm test tests/auth-failure-contract.test.ts
```

## プログラム本体で残りうる実装（担当分担）

テストは **現行コード** に対して GREEN。以下は **本体実装担当** の推奨方針である。実装後は契約テストを **意図的に** 更新する。

### 1. JWKS 取得失敗（API）— 担当: API / 優先度: 高

**現状:** `fetch_jwks` の `httpx` エラーや `jwks_provider` の未捕捉例外 → 500 internal-error（401 にはならない）。

**推奨（段階的）:**


| フェーズ                      | 推奨                       | 理由                                   |
| ------------------------- | ------------------------ | ------------------------------------ |
| **Week 2 クローズ（Step 4〜5）** | **コード変更なし（現状 500 のまま）**  | 契約テストが固定済み。token 不正とインフラ障害の分離は満たしている |
| **本番前（Week 11 運用準備）**     | **503 + 専用 Problem** へ昇格 | クライアントが「再試行可能な障害」と判別しやすい             |


**Week 11 で 503 にする場合の推奨実装:**

1. `hibi/core/errors.py` に `ServiceUnavailableError(ApplicationError)` を追加する
  - `problem_type = "service-unavailable"`  
  - `status = 503`  
  - `detail` は固定文言（例: `Authentication service is temporarily unavailable.`）。`str(exception)` は使わない
2. `**hibi/api/dependencies.py` の `fetch_jwks` のみ**で `httpx` の `ConnectError` / `TimeoutException` を捕捉し、上記例外に変換する
3. `**JwtVerifier` 内ではインフラ例外を 401 に変換しない**（署名・claim 失敗だけ `TokenVerificationError` → `AuthenticationError`）
4. OpenAPI の `/me` 等に **503 レスポンス**を追加し、`pnpm openapi:client` を再実行する
5. `test_jwks_provider_failure_returns_500_not_401` を **503 + service-unavailable** 期待に更新する（テスト名も合わせて変更）

**ログ:** `requestId` 付きで WARN/ERROR。JWKS URL・token・レスポンス body はログに載せない。

**非推奨:** すべての `Exception` を 401 に潰す、JWKS 失敗時に「ログインし直してください」だけ返す。

---

### 2. `get_jwt_verifier` の `@lru_cache` — 担当: API / 優先度: 低（Week 2）

**推奨:** **Week 2 では変更しない。** 設定（`HIBI_SUPABASE_URL` 等）はデプロイ単位で固定し、変更時は **プロセス再起動** と runbook に明記する。

**将来（任意）:** `/health/ready` で JWKS endpoint への到達性だけ確認し、Render/Vercel の ready プローブに使う（Week 11）。verifier の cache クリア API は不要。

---

### 3. アカウント画面の 401 扱い（Web）— 担当: Web / 優先度: 中

**推奨 UX（現行コード方針を維持）:**


| 条件                                            | 動作                                                         |
| --------------------------------------------- | ---------------------------------------------------------- |
| `getUser()` なし                                | `/login` へ redirect                                        |
| `getCurrentUserFromApi()` → `unauthenticated` | `/login` へ redirect                                        |
| API → **401 Problem**（期限切れ・不正 token 等）        | `**ApiErrorMessage` を表示**（redirect しない）                    |
| API → **500 / 503**                           | `**ApiErrorMessage`**（「認証に失敗」と混同しない文言は `presentProblem` 側） |


**推奨実装（小さく足すなら）:**

- `ApiErrorMessage` 直下に **「再ログイン」** リンク（`/login`）を 401 Problem 時だけ表示する  
- 401 Problem 時も `/login` へ **自動 redirect しない**（Step 4 Web 契約テストと整合）

**非推奨:** 401 Problem をすべて `unauthenticated` に畳み込んで redirect だけにする（インフラ障害と区別不能）。

---

### 4. Supabase SSR の session 更新 — 担当: Web / 優先度: 高（Step 5 の前）

**現状:** `apps/web/src/proxy.ts` にロジックあり。**Next のエントリに未配線**の可能性がある。

**推奨実装:**

1. [Supabase Auth + Next.js Server Side](https://supabase.com/docs/guides/auth/server-side/nextjs) の **最新推奨**（Next.js 16 の middleware / proxy 規約）に従い、`proxy.ts` を **全リクエストで `getUser()` して Cookie を更新**する
2. **route 保護は UX のみ**（未ログインを `/login` へ）。認可は FastAPI に任せる（[07-security-auth.md](./07-security-auth.md)）
3. Step 5 の Playwright / Local 縦切り **の前** に配線し、ログイン直後の Server Component で session が欠けないことを確認する

**触るファイル:** `apps/web/src/proxy.ts`、必要なら `middleware.ts` またはフレームワーク指定のエントリ

---

### 5. ログイン UX — 担当: Web / 優先度: 中（Week 2 仕上げ）

**推奨:**

- `signInAction` 失敗時の `?error=invalid-credentials` を `**login/page.tsx` で読み、`Alert` 表示**  
- サインアップ UI は **Week 2 必須外**。Local では Studio / Auth API でユーザ作成（運用ドキュメントに記載済み）

**非推奨:** クライアント hook に `signInWithPassword` を移して Server Action をやめる（SSR Cookie 方針とずれる）。

---

### 6. Step 5: Supabase Local 統合 — 担当: API + Web / 優先度: Week 2 完了に必要

**推奨:**

1. スクリプトまたは pytest マーカー `@pytest.mark.integration` で **Supabase Local 前提**のテストを分離
2. 固定テストユーザーで password login → **実 access token** → `GET /me` が 200
3. 同 token を改ざん / ヘッダなし → **401 Problem**（Step 4 と同じ body 形状）
4. CI では Step 4 の **決定的テストのみ**回し、integration は nightly または手動（Week 2 一人開発ならローカル + ドキュメントでも可）

**触る候補:** `apps/api/tests/`（新規 `test_auth_supabase_local.py` 等）、`scripts/`、CI workflow

---

### 7. OpenAPI / クライアント — 担当: API + Web / 随時

**推奨:** Problem `type` や status（503 等）を変えた **同一 PR** 内で必ず:

```sh
pnpm openapi:client
```

生成 diff を commit し、CI で `typecheck` / client テストが通ることを確認する。

## 認証処理の流れ（参照）

```text
GET /api/v1/me
  Authorization: Bearer <access_token>
    → HTTPBearer
    → get_principal
      → JwtVerifier.verify
        → jwks_provider / JWKS cache
        → jwt.decode(iss, aud, exp, alg)
      → 失敗: AuthenticationError → 401 Problem (unauthorized)
      → JWKS インフラ例外（未処理）: Exception handler → 500 Problem (internal-error)
```

## Step 5 との関係


| Step           | 内容                                                                |
| -------------- | ----------------------------------------------------------------- |
| **4（本ドキュメント）** | 固定 JWKS + TestClient による **決定的な契約テスト**                            |
| **5**          | Supabase Local の **実 access token**、login → `/me`、改ざん token の統合検証 |


Week 2 完了条件「token なし、期限切れ、不正 token が 401 Problem」は **Step 4 + Step 5** の合わせ技とする。

## 関連ドキュメント

- [認証・セキュリティ方針](./07-security-auth.md)
- [エラーハンドリング方針](./04-error-handling.md)
- [テスト・品質管理方針](./08-testing-quality.md)
- [実装スケジュール Week 2](./11-implementation-schedule.md)

