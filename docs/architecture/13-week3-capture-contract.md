# Week 3: Capture 業務ルールと API 契約

## 目的

Week 3 は、ユーザーが打ち込んだ**未整理の生入力 1 件（Capture）**を、AI なしで FE から PostgreSQL まで同期で保存・閲覧・更新・削除できるようにする。

このドキュメントは次を固定する。

- Capture の業務ルール
- HTTP / OpenAPI 契約
- スキーマと認可
- 既存方針に沿った推奨実装

完了条件は [実装スケジュール](./11-implementation-schedule.md) の Week 3 に従う。

- AI なしで Capture CRUD が FE から PostgreSQL まで E2E で動作する
- 同一冪等キーによる重複作成が発生しない
- 別ユーザーの Capture が取得できない

## 既存方針からの拘束条件

新規判断の前に、定義済みドキュメントを優先する。


| ドキュメント                                                                   | この週に効く拘束                                                                          |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| [01-architecture.md](./01-architecture.md)                               | 業務 API は FastAPI のみ。Web は業務 table を直接操作しない。Capture 作成は `Idempotency-Key` 付き       |
| [02-project-structure.md](./02-project-structure.md)                     | `modules/captures/`、`features/capture/`、migration は `supabase/migrations` のみ      |
| [03-naming-conventions.md](./03-naming-conventions.md)                   | `MAX_CAPTURE_LENGTH = 2_000`、`operationId`、`Request`/`Response`、table `captures`  |
| [04-error-handling.md](./04-error-handling.md)                           | RFC 9457。別ユーザー所有は 404。業務層で `HTTPException` を上げない                                  |
| [06-api-data-contracts.md](./06-api-data-contracts.md)                   | `/api/v1`、`data` エンベロープ、cursor 一覧、201/202/204、冪等キー                                |
| [07-security-auth.md](./07-security-auth.md)                             | Principal + 所有者条件。認可は FastAPI。private schema                                      |
| [08-testing-quality.md](./08-testing-quality.md)                         | 認可・冪等性を重点。SQLite で PostgreSQL を代替しない                                              |
| [12-week2-auth-failure-contract.md](./12-week2-auth-failure-contract.md) | 未認証は 401 Problem Details。JWKS 障害は 401 にしない                                        |
| foundation migration                                                     | 業務 table は `app` schema。`anon`/`authenticated` から revoke。`hibi_runtime` にだけ GRANT |


Week 3 では Jev / LLM / outbox / Worker / retry / polling を実装しない。それらは Week 4 以降の契約変更として予約する。

## ドメイン定義

Capture は「ユーザーが今思いついたことを、まだ分類せずに残した 1 件」である。チャットのプロンプト消費ではなく、所有者付きの永続 resource である。

Week 3 の正は **生テキストとその保存状態** だけとする。

```text
Browser
  → Next.js（入力 UI・session・生成 client）
    → FastAPI（認可・検証・冪等・CRUD）
      → PostgreSQL app.captures
```

処理パイプライン（outbox → Worker → Jev）は Week 4 以降。Week 3 の `status` は常に `pending` で、遷移しない。

## 検討した方針と推奨



### 作成 API の status code


| 案   | 内容                                                              | 採用                                                                 |
| --- | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| A   | Week 3 は同期作成なので `201 Created`。Week 4 で `202 Accepted` へ意図的に変更する | **採用**                                                             |
| B   | Week 3 から `202` を返す（job は無い）                                    | 不採用。同期保存なのに非同期受理を偽る                                                |
| C   | 作成は常に `201`、処理開始は別 endpoint                                     | 不採用。[01](./01-architecture.md) と Week 4 完了条件が「作成 API が 202」と明記している |


[06-api-data-contracts.md](./06-api-data-contracts.md) は「作成は 201、job 受理は 202」と分けている。Week 3 は作成、Week 4 は作成と同時に処理開始、と読む。

`201` → `202` は [06](./06-api-data-contracts.md) 上の破壊的変更である。Week 4 で契約テストと OpenAPI を**意図的に**更新し、本ドキュメントに変更理由を追記する。

### 永続化


| 案   | 内容                                  | 採用                                                                                                                                             |
| --- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| A   | SQLAlchemy 2.0 async + 既存 `asyncpg` | **採用**。[02](./02-project-structure.md) の `models.py`、[08](./08-testing-quality.md) の repository 前提と一致。Week 4 の同一 transaction + outbox にそのまま使える |
| B   | `asyncpg` 生 SQL のみ                  | 不採用。小さく始められるが、UoW / session 境界を後から取り直すコストが大きい                                                                                                  |


SQLite は使わない。

### 削除


| 案   | 内容                 | 採用                                           |
| --- | ------------------ | -------------------------------------------- |
| A   | 物理削除 + `204`       | **採用**。Week 3 の inbox CRUD に十分。冪等キーも行と一緒に消える |
| B   | `is_archived` 論理削除 | 不採用。命名例にはあるが、検索・レビュー要件が出るまで YAGNI            |




## 業務ルール



### 所有と可視性

- Capture は必ず検証済み Principal の `user_id` に紐づく
- 作成時の `user_id` は token の `sub` だけから決める。body / query で付け替えない
- Repository のすべての query に `user_id` を含める
- 存在しない ID と、別ユーザー所有はどちらも `404 capture-not-found`（存在を秘匿）
- `403` は使わない（認証済みだが他者 resource、という情報を返さない）



### 入力

- 必須は `rawText` のみ
- 前後空白は trim する
- trim 後の長さは 1 以上 2,000 以下（`MAX_CAPTURE_LENGTH`）
- 空、空白のみ、2,000 超は 422
- 改行は本文として許可する
- 添付、HTML、位置情報、カテゴリ指定は Week 3 対象外
- user 入力を HTML として描画しない



### 状態（Week 3）

```text
pending | processing | completed | failed
```

DB と API の enum は Week 4 以降の値を先に許可する。Week 3 の API は `pending` 以外を書き込まない。

- 作成直後: `pending`
- 更新・削除: `pending` の間は常に許可
- `processing` 以降の遷移・更新禁止・retry は Week 4 で追加する



### 冪等（作成のみ）

`POST /api/v1/captures` は `Idempotency-Key` 必須。

- スコープは `(user_id, Idempotency-Key)`
- payload hash は trim 後 `rawText` の SHA-256 hex
- 同じ key・同じ hash: 最初に作成した Capture を返す（新規 insert しない）
- 同じ key・異なる hash: `409 idempotency-key-conflict`
- key 欠落: `400 idempotency-key-required`
- key 形式不正: `400 idempotency-key-invalid`
- PATCH / DELETE に冪等キーは要求しない（Week 3）
- retention: Capture 行の寿命に一致する。削除後は同じ key で新規作成してよい
- クライアントは「1 回の投稿意図」ごとに UUID を発行する。再送時だけ同じ key を再利用する



### 一覧

- 自分の Capture だけ
- 並びは `created_at DESC, id DESC`（安定）
- pagination は cursor
- Week 3 に status / 全文検索 filter は置かない



### 更新

- `rawText` のみ変更できる
- `id` / `userId` / `status` / 時刻はクライアントから変更できない
- 対象が無ければ 404



### 削除

- 所有者のみ物理削除
- 成功は `204`
- 再削除は 404



## データモデル

関係図は [ER図](./14-er.md)、列・制約・権限は [テーブル定義](./15-table-catalog.md) を正の読み物とする。DDL の正は `supabase/migrations/20260927090452_captures.sql` である。

推奨 DDL（`app` schema、foundation と同じ権限モデル。実装済み）:

```sql
create table if not exists app.captures (
  id uuid primary key,
  user_id uuid not null references app.profiles(user_id) on delete cascade,
  raw_text text not null,
  status text not null default 'pending',
  idempotency_key text not null,
  request_hash text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint ck_captures__raw_text_length
    check (char_length(raw_text) >= 1 and char_length(raw_text) <= 2000),
  constraint ck_captures__status
    check (status in ('pending', 'processing', 'completed', 'failed')),
  constraint ck_captures__idempotency_key_length
    check (char_length(idempotency_key) >= 8 and char_length(idempotency_key) <= 128),
  constraint ck_captures__request_hash_sha256
    check (request_hash ~ '^[0-9a-f]{64}$'),
  constraint uq_captures__user_id_idempotency_key
    unique (user_id, idempotency_key)
);

create index if not exists ix_captures__user_id_created_at
  on app.captures (user_id, created_at desc, id desc);

revoke all on app.captures from public, anon, authenticated;
grant select, insert, update, delete on app.captures to hibi_runtime;
```

規則:

- 公開 ID は UUID。アプリケーションで `uuid.uuid7()` を発行する（例示 ID `019...` と cursor の時間順に合わせる）
- 文字列は `text` + check。`varchar(n)` は使わない
- 時刻は `timestamptz`
- 変更頻度の高い status は DB enum ではなく check constraint（[06](./06-api-data-contracts.md)）
- `user_id` は FK なので複合 index の左端でカバーする（CASCADE / 所有者 query 用）
- RLS は foundation の `app.profiles` と同様、Week 3 では追加しない。防御は private schema + revoke + runtime role + repository の所有者条件
- `idempotency_key` / `request_hash` は API response に出さない

Week 4 以降で足す列（この週は作らない）: `processed_at`、route、category、urgency、policy/model version、outbox 行。

## HTTP 契約

Base path: `/api/v1`  
認証: すべて `Authorization: Bearer`。失敗は Week 2 と同じ 401 Problem Details。  
JSON field: `camelCase`  
日時: UTC の RFC 3339  
成功 body: `data` エンベロープ。エラーは RFC 9457（`data` で包まない）

### Resource 型

```json
{
  "id": "0198f0c2-7c1a-7000-8000-000000000001",
  "rawText": "牛乳を買う",
  "status": "pending",
  "createdAt": "2026-09-27T08:00:00Z",
  "updatedAt": "2026-09-27T08:00:00Z"
}
```

- `userId` は返さない（所有者は Principal で確定済み）
- 単一も一覧要素も `CaptureResponse` を使う。`CaptureListItem` は作らない
- 一覧の HTTP 型は `ApiResponseWithMeta[list[CaptureResponse], CursorMeta]`。`CaptureListResponse` を別 item 型としては作らない



### `POST /api/v1/captures`

- `operationId`: `createCapture`
- Header: `Idempotency-Key` 必須。印字可能 ASCII、長さ 8〜128
- CORS `allow_headers` に `Idempotency-Key` を追加する（現行は `Authorization` / `Content-Type` / `X-Request-ID` のみ）

Request:

```json
{
  "rawText": "牛乳を買う"
}
```

初回成功:


| 項目         | 値                              |
| ---------- | ------------------------------ |
| Status     | `201`                          |
| `Location` | `/api/v1/captures/{captureId}` |
| Body       | `{ "data": CaptureResponse }`  |


同一 key・同一 payload の再送: `200` + 最初の `CaptureResponse`（新規作成しない）。`Location` は付けてよい。

### `GET /api/v1/captures/{captureId}`

- `operationId`: `getCapture`
- 成功: `200` + `{ "data": CaptureResponse }`



### `GET /api/v1/captures`

- `operationId`: `listCaptures`
- Query: `limit`（default 20、1〜50）、`cursor`（optional、不透明）

```json
{
  "data": [
    {
      "id": "0198f0c2-7c1a-7000-8000-000000000001",
      "rawText": "牛乳を買う",
      "status": "pending",
      "createdAt": "2026-09-27T08:00:00Z",
      "updatedAt": "2026-09-27T08:00:00Z"
    }
  ],
  "meta": {
    "nextCursor": "eyJjIjoiMjAyNi0wOS0yN1QwODowMDowMFoiLCJpIjoiMDE5OGYwYzItN2MxYS03MDAwLTgwMDAtMDAwMDAwMDAwMDAxIn0",
    "hasNextPage": false
  }
}
```

cursor は `(createdAt, id)` をエンコードした不透明文字列とする。SQL 条件をそのまま露出さない。不正 cursor は `400 malformed-cursor`。

### `PATCH /api/v1/captures/{captureId}`

- `operationId`: `updateCapture`
- 成功: `200` + `{ "data": CaptureResponse }`
- `updatedAt` を更新する。中身が同じでも 200 でよい

Request:

```json
{
  "rawText": "低脂肪乳を買う"
}
```



### `DELETE /api/v1/captures/{captureId}`

- `operationId`: `deleteCapture`
- 成功: `204`（body なし）



### Week 3 で作らない endpoint

- `POST /api/v1/captures/{captureId}/retry`
- 処理状態専用の polling 専用 API（GET 単体で足りる）



## エラー契約

`type` で分岐する。`detail` 文字列では分岐しない。`requestId` は `X-Request-ID` と一致。`instance` は request path。


| ケース                  | Status | `type` 末尾                  | `title`                     | 備考                              |
| -------------------- | ------ | -------------------------- | --------------------------- | ------------------------------- |
| 未認証 / token 不正       | 401    | `unauthorized`             | `Unauthorized`              | Week 2 と同じ。例外メッセージ直出し禁止         |
| `Idempotency-Key` なし | 400    | `idempotency-key-required` | `Idempotency-Key required`  | 固定 `detail`                     |
| key 形式不正             | 400    | `idempotency-key-invalid`  | `Idempotency-Key invalid`   | 長さ・文字種                          |
| 不正 cursor            | 400    | `malformed-cursor`         | `Malformed cursor`          |                                 |
| 同一 key・異なる payload   | 409    | `idempotency-key-conflict` | `Idempotency-Key conflict`  |                                 |
| 存在しない / 他者の Capture  | 404    | `capture-not-found`        | `Capture not found`         | 両者を区別しない                        |
| `rawText` 検証失敗       | 422    | `validation-error`         | `Request validation failed` | `errors[].pointer` は `/rawText` |
| path の UUID 不正       | 422    | `validation-error`         | `Request validation failed` |                                 |
| JWKS 等インフラ例外         | 500    | `internal-error`           | `Internal server error`     | 401 にしない                        |
| その他の未処理例外            | 500    | `internal-error`           | `Internal server error`     |                                 |


404 例:

```json
{
  "type": "https://api.hibi.example/problems/capture-not-found",
  "title": "Capture not found",
  "status": 404,
  "detail": "The requested capture does not exist.",
  "instance": "/api/v1/captures/0198f0c2-7c1a-7000-8000-000000000099",
  "requestId": "019..."
}
```

422 例は [04-error-handling.md](./04-error-handling.md) の `/rawText` + `too_long` に合わせる。

固定 `detail`（例外メッセージを使わない）:

- `idempotency-key-required`: `Idempotency-Key header is required.`
- `idempotency-key-invalid`: `Idempotency-Key is invalid.`
- `idempotency-key-conflict`: `Idempotency-Key was reused with a different payload.`
- `malformed-cursor`: `The pagination cursor is invalid.`
- `capture-not-found`: `The requested capture does not exist.`

`problem_responses` に 400 / 409 を追加する。

## レイヤーと型

[01](./01-architecture.md) と [02](./02-project-structure.md) に従う。

```text
router.py        HTTP 変換、status、Location、header
service.py       トランザクション、冪等判定、CreateCaptureCommand
repository.py    user_id 必須の永続化。get_by_id は無ければ None
models.py        SQLAlchemy。response に使わない
schemas.py       CreateCaptureRequest 等の境界型
errors.py        CaptureNotFoundError 等（HTTP を知らない）
policies.py      Week 3 では作らない（遷移規則がまだ無い）
```

内部型（API 境界に出さない）:

```text
CreateCaptureCommand
CreateCaptureResult
UpdateCaptureCommand
ListCapturesQuery
Capture
```

Router は `HTTPException` を上げない。Service が型付き例外を上げ、Global Exception Handler が Problem Details にする。

`get_principal` を全 Capture endpoint に付ける。既存 `/me` と同じ dependency。

DB は `hibi/db` に async session / Unit of Work を新設する。例外時 rollback は session dependency が保証し、exception handler は rollback しない（[04](./04-error-handling.md)）。

## Web 契約



### 画面

モバイル前提の 2 面。


| 経路                      | 役割                                        |
| ----------------------- | ----------------------------------------- |
| `/captures`             | 入力欄 + 自分の一覧。empty / loading / error を必ず持つ |
| `/captures/[captureId]` | 本文表示、編集、削除。他者・不存在は `notFound()`           |


未ログインは Week 2 アカウント画面と同じく `getUser()` → `/login`。

`unauthenticated` も `/login`。401 Problem や 5xx は redirect せず `ApiErrorMessage` を出す（[12](./12-week2-auth-failure-contract.md)）。

### 呼び出し

- 業務 API の代替 Route Handler は作らない
- Server Action 名: `createCaptureAction` / `updateCaptureAction` / `deleteCaptureAction`
- 生成 client の `createCapture` / `getCapture` / `listCaptures` / `updateCapture` / `deleteCapture` を使う
- 手書きの Capture 型を作らない。`pnpm openapi:client` を同一 PR で回す
- 表示文言は FE が決める。API の `detail` をそのまま見出しにしない



### 冪等キーの発行

`CaptureForm` は Client Component とし、**投稿意図ごとに** `crypto.randomUUID()` を 1 つ持つ。

- 二重送信・通信リトライは同じ key を送る
- 成功後、またはユーザーが本文を消して次のメモを書き始めたときに新しい key を発行する
- Server Action 側で毎回新しい UUID を振らない（再送が二重作成になる）

422 の `errors` は `pointer === "/rawText"` を入力欄へ出す。

Week 3 の UI に処理中 polling、retry、カテゴリ表示は出さない。`status` は受け取っても描画しなくてよい。

## 推奨実装順

週 10 時間前提で、テストを先に固定する。

1. **契約テスト（API）**
  TestClient + `get_principal` override で 201/200 replay/409/404 秘匿/422/401 を先に落とす。DB は repository fake でよい。
2. **migration**
  `supabase migration new` で `app.captures` を追加。`supabase/tests` に revoke と owner query 用の検証を足す。
3. **DB 接続基盤**
  方針は [16-week3-db-repository.md](./16-week3-db-repository.md)。engine / session だけ。
4. **Capture Repository**
  方針は [17-week3-capture-repository.md](./17-week3-capture-repository.md)。`modules/captures/models.py` と `repository.py`。`db/crud/` は作らない。
5. **Capture Service**
  方針は [18-week3-capture-service.md](./18-week3-capture-service.md)。冪等・trim・cursor・domain error。HTTP はまだしない。
6. **router / OpenAPI**
  `create_app` から captures router を mount。`problem_responses` を更新。`pnpm openapi:client`。
7. **Web**
  `/captures` と detail。Server Action は token を Bearer で渡す（`getCurrentUserFromApi` と同じ取得方法）。
8. **縦切り確認**
  ログイン済みユーザーが作成 → 一覧 → 編集 → 削除。別ユーザーの URL を開いても 404。



## テスト契約



### API（決定的・CI）


| ケース                        | 期待                                                             |
| -------------------------- | -------------------------------------------------------------- |
| 未認証で POST/GET/PATCH/DELETE | 401 `unauthorized`                                             |
| 正常作成                       | 201、`Location`、`data.status === "pending"`、`rawText` が trim 済み |
| 同一 key・同一 body 再 POST      | 200、同じ `id`、行は 1 件                                             |
| 同一 key・異なる `rawText`       | 409 `idempotency-key-conflict`                                 |
| `Idempotency-Key` なし       | 400                                                            |
| `rawText` 空 / 2001 文字      | 422、`/rawText`                                                 |
| 自分の GET                    | 200                                                            |
| 他人の ID で GET/PATCH/DELETE  | 404 `capture-not-found`（401/403 ではない）                          |
| 存在しない ID                   | 404                                                            |
| 一覧に他人の行が混ざらない              | `data` が所有者のみ、新しい順                                             |
| DELETE 後 GET               | 404                                                            |
| JWKS 障害中の GET              | 500（401 ではない）。既存 verifier 契約を流用                                |




### API（integration・Local）

既存 Step 5 と同様 `@pytest.mark.integration`。実 token で作成し、DB に `user_id` が載ること、Data API（`anon`/`authenticated`）から `app.captures` を読めないことを確認する。

### Web


| ケース                | 期待                             |
| ------------------ | ------------------------------ |
| 未ログインで `/captures` | `/login`                       |
| 作成成功               | 一覧に本文が出る                       |
| 空送信                | 入力欄エラー（422）                    |
| 一覧 empty           | empty state                    |
| API 500            | `ApiErrorMessage`（login へ飛ばない） |
| 二重 submit          | 1 件だけ作られる（同じ Idempotency-Key）  |




## 脅威（Week 3 分）

[07](./07-security-auth.md) の最低限モデルのうち、この週で潰すもの。

- IDOR/BOLA: すべての query に `user_id`。他者は 404
- `user_id` 付替え: body に所有者を受けない
- Data API 経由の読み出し: `app` を expose しない、GRANT しない
- XSS: `rawText` を HTML として出さない
- 冪等キーの取り違え: hash 不一致は 409。他ユーザーと同じ key でも行は分離
- secret: token / hash 以外の内部値を log に出さない。log に載せるのは `requestId` と `captureId`

file upload、webhook、vector 漏洩、prompt injection は対象外。

## Week 4 以降へ予約する変更

実装しないが、壊さないために列と enum を先に空ける。


| 時期     | 変更                                                         | 備考                                  |
| ------ | ---------------------------------------------------------- | ----------------------------------- |
| Week 4 | 作成が `202`、outbox 同一 transaction、`processing` 遷移、polling UI | 本契約の 201 テストを意図的に更新                 |
| Week 4 | `POST .../retry`                                           | `failed` のみ                         |
| Week 4 | `pending` / `processing` 中の更新ルール                           | 処理開始後は本文更新を 409 にする想定               |
| Week 5 | route / category / urgency / confidence                    | response への追加は optional field なら非破壊 |
| Week 8 | 検索                                                         | 一覧 query を拡張                        |




## プログラム本体の推奨（担当分担）

テストを先に GREEN にしたあと、本体は次を小さく入れる。

### 1. CORS と OpenAPI — 担当: API / 必須

`create_app` の `allow_headers` に `Idempotency-Key` を足す。各 Capture 操作に `responses=problem_responses(...)` を付ける。client 再生成を同じ PR に含める。

### 2. ApplicationError の追加 — 担当: API / 必須

`CaptureNotFoundError`、`IdempotencyKeyRequiredError`、`IdempotencyKeyInvalidError`、`IdempotencyKeyConflictError`、`MalformedCursorError` を `ApplicationError` 配下に置く。`str(exception)` を `detail` に使わない。

### 3. DB 接続 — 担当: API / 必須

`HIBI_DATABASE_URL`（既存 `.env.example`）で async engine を張る。runtime は `hibi_runtime_user`。service role は使わない。

### 4. Web の入力 UX — 担当: Web / 必須

送信中は button を disable する。失敗はフォーム近くに残す（toast だけにしない）。削除は確認のあと `deleteCaptureAction`。

## 関連ドキュメント

- [アーキテクチャ方針](./01-architecture.md)
- [プロジェクト構成](./02-project-structure.md)
- [命名規約](./03-naming-conventions.md)
- [エラーハンドリング](./04-error-handling.md)
- [API・データ契約](./06-api-data-contracts.md)
- [認証・セキュリティ](./07-security-auth.md)
- [テスト・品質管理](./08-testing-quality.md)
- [実装スケジュール](./11-implementation-schedule.md)
- [Week 2 認証失敗契約](./12-week2-auth-failure-contract.md)

