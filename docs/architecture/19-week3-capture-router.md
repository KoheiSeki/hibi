# Week 3 Step 6: Capture Router / OpenAPI

[Capture 契約](./13-week3-capture-contract.md) の実装順 6。[Capture Service](./18-week3-capture-service.md) の戻りと例外を、HTTP / OpenAPI にする。Web は次ステップ。

## このステップのゴール

`POST/GET/PATCH/DELETE /api/v1/captures` が、既存の `get_principal` と Global Exception Handler の上で契約どおり動く。trim・冪等・cursor の意味判断は Service のまま。

完了条件:

- 全 Capture endpoint に `Depends(get_principal)`
- `user_id` は Principal だけ。body / query / path から所有者を付け替えない
- Router は `HTTPException` を上げない。Service の例外をそのまま上げる
- 初回作成は `201` + `Location`。同じ key・同じ本文は `200`（`CreateCaptureResult.created`）
- 一覧は `ApiResponseWithMeta[list[CaptureResponse], CursorMeta]`
- 削除成功は `204`（body なし）
- CORS `allow_headers` に `Idempotency-Key`
- `problem_responses` に 400 / 409 がある
- `uv run --project apps/api python scripts/export_openapi.py` と `pnpm openapi:client` を同じ変更に含める
- TestClient + `get_principal` override で [契約テスト](./13-week3-capture-contract.md#テスト契約) の HTTP 行を通常 CI で確認する



## やらないこと


| 先送り                                                    | 理由                                                |
| ------------------------------------------------------ | ------------------------------------------------- |
| Web / Server Action                                    | 実装順 7                                             |
| `policies.py`                                          | 状態遷移がまだ無い                                         |
| Service の trim / hash / cursor を Router に移す            | [18](./18-week3-capture-service.md) が正            |
| `session.commit()`                                     | [16](./16-week3-db-repository.md) の `get_session` |
| 実 PostgreSQL の integration                             | このステップの決定的テストは fake Service（または fake Repository）  |
| `userId` / `idempotencyKey` / `requestHash` を JSON に出す | 契約                                                |




## 依存の流れ

```text
HTTP
  → get_principal
  → get_session → CaptureRepository → CaptureService
    → command / query
      → domain Capture / CreateCaptureResult / CapturePage
    → ApplicationError
      → handle_application_error → Problem Details
  → ApiResponse / ApiResponseWithMeta / 204 / Location
```

```text
Router は status と JSON 形だけを知る
Service は HTTP を知らない
Pydantic Request は HTTP 境界だけ
```



## 作成・変更ファイル



### 新規


| ファイル                                            | 要点                                                                             |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| `apps/api/src/hibi/modules/captures/schemas.py` | `CreateCaptureRequest` / `UpdateCaptureRequest` / `CaptureResponse`。`ApiModel` |
| `apps/api/src/hibi/modules/captures/router.py`  | `APIRouter`。endpoint 関数名は [命名](./03-naming-conventions.md)                     |
| `apps/api/tests/test_capture_api.py`            | TestClient。通常 CI                                                               |




### 変更


| ファイル                                                             | 要点                                                        |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| `apps/api/src/hibi/api/main.py`                                  | 1. `include_router`。CORS に `Idempotency-Key`              |
| `apps/api/src/hibi/api/schemas.py`                               | 共通 `ApiResponseWithMeta` / `CursorMeta`（モジュールに置かない）       |
| `apps/api/src/hibi/api/openapi.py`                               | `_DESCRIPTIONS` に 400 / 409                               |
| `apps/api/src/hibi/api/exception_handlers.py`                    | `CaptureTextInvalidError` 相当で `errors[].pointer=/rawText` |
| `apps/api/src/hibi/api/dependencies.py` または `captures/router.py` | `get_capture_service`（session + repository を組み立て）         |
| `contracts/openapi.json`                                         | `scripts/export_openapi.py`                               |
| `packages/api-client/src/generated/`                             | `pnpm openapi:client`                                     |


`service.py` の業務ルールは変えない。`errors.py` の `problem_type` も変えない。

`api/routers.py` は、endpoint が増えてからでよい。今は `create_app` から `include_router` する。

## 実装要点



### 共通エンベロープ

[06](./06-api-data-contracts.md) の型を `hibi.api.schemas` に足す。Capture 専用の `CaptureListResponse` は作らない。

```text
ApiResponseWithMeta[DataT, MetaT]
  data
  meta

CursorMeta
  next_cursor: str | None
  has_next_page: bool
```

JSON は既存 `ApiModel` の camelCase（`nextCursor` / `hasNextPage`）。

### `schemas.py`（captures）

```text
CreateCaptureRequest
  raw_text: str

UpdateCaptureRequest
  raw_text: str

CaptureResponse
  id: UUID
  raw_text: str
  status: str
  created_at: datetime
  updated_at: datetime
```

- `user_id` / 冪等キー / hash は置かない
- 長さの最終判定は Service（trim 後）。Request に `max_length=2000` を付けても、空白のみは Pydantic を通る
- 欠落した `rawText` は FastAPI の 422（既存 `handle_request_validation_error`）
- domain `Capture` を `response_model` に使わない

写しは Router 内の private（`_to_capture_response`）でよい。

### Header と Query

`POST` の `Idempotency-Key` は **Header を required にしない**。欠落を FastAPI の 422 にすると、契約の 400 `idempotency-key-required` にならない。`str | None` で受けて command に渡す。形式も Service が判定する。

```text
Header(alias="Idempotency-Key")  →  CreateCaptureCommand.idempotency_key
```

一覧:

```text
limit: default 20、Query(ge=1, le=50)
cursor: optional str
```

範囲外の `limit` は Query の 422。Service の clamp は防御用のまま。

path の UUID 不正は 422。Python 名は `capture_id`。OpenAPI の path も `{capture_id}` でよい。

### `get_capture_service`

```text
session = Depends(get_session)
CaptureService(session, CaptureRepository(session))
```

Router が `CaptureRepository` や SQLAlchemy を直接叩かない。テストは `get_capture_service`（または同等）を fake に差し替える。`get_principal` は既存どおり override。

### endpoint


| HTTP                                   | 関数               | 成功                                    | 備考                                            |
| -------------------------------------- | ---------------- | ------------------------------------- | --------------------------------------------- |
| `POST /api/v1/captures`                | `create_capture` | `created is True` → 201、`False` → 200 | どちらも `Location: /api/v1/captures/{id}` を付けてよい |
| `GET /api/v1/captures/{capture_id}`    | `get_capture`    | 200                                   |                                               |
| `GET /api/v1/captures`                 | `list_captures`  | 200 + meta                            | `CapturePage` をエンベロープへ                        |
| `PATCH /api/v1/captures/{capture_id}`  | `update_capture` | 200                                   |                                               |
| `DELETE /api/v1/captures/{capture_id}` | `delete_capture` | 204                                   | `response_model` なし。`return None`             |


`operationId` は `createCapture` / `getCapture` / `listCaptures` / `updateCapture` / `deleteCapture`。

`responses=problem_responses(...)` の目安:


| 操作     | status                  |
| ------ | ----------------------- |
| POST   | 400, 401, 409, 422, 500 |
| GET 単体 | 401, 404, 422, 500      |
| GET 一覧 | 400, 401, 422, 500      |
| PATCH  | 401, 404, 422, 500      |
| DELETE | 401, 404, 422, 500      |


禁止:

- `HTTPException`
- body の `userId`
- domain `Capture` をそのまま返す
- 例外を Router で status に変換する（Handler の仕事）



### 201 / 200

デコレータを `status_code=201` 固定にすると replay が壊れる。`Response` の `status_code` を `created` で切り替える。

### `errors[]`（422 from Service）

空白のみなど、Pydantic を通ったあとの `CaptureTextInvalidError` は、今の handler だと `errors[]` が付かない。契約の FE は `pointer === "/rawText"` を見る。

`handle_application_error` で、pointer を持つ例外だけ `FieldProblem` を付ける。`CaptureTextInvalidError` に `pointer = "/rawText"` と `error_code`（例: `"invalid"`）をクラス属性で置いてよい。`errors.py` は `problem_details` を import しない。

欠落 `rawText` と path UUID 不正は、これまでどおり `RequestValidationError`。

### CORS / OpenAPI

```text
allow_headers = Authorization, Content-Type, X-Request-ID, Idempotency-Key
```

```text
uv run --project apps/api python scripts/export_openapi.py
pnpm openapi:client
```

CI は OpenAPI と生成 client の未 commit 差分で落とす。手で `generated/` を編集しない。

## テスト方針（このステップ）

`test_capture_api.py`。DB に繋がない。`get_principal` と `get_capture_service` を override する。

fake Service がやること:

- `create` の `created=True/False` をテストが指定する
- `get` / `update` / `delete` は所有者 ID が違うと `CaptureNotFoundError`
- `list` は渡された `ListCapturesQuery.user_id` だけを返す
- 不正 cursor は `MalformedCursorError`（実 decode を Router がやらなければ、fake が上げる。decode は Service なので、一覧の不正 cursor テストは **実 Service + fake Repository** でもよい）

不正 cursor と trim 済み 201 は、HTTP と Service の境にある。次のどちらか一方で足りる。

- A: fake Repository + 実 `CaptureService`（session はメモリ不要。Service は rollback 以外 session を使わない。IntegrityError テストは Service unit 済み）
- B: fake Service で status だけ見て、cursor / trim は `test_capture_service.py` に任せる

推奨は **B を主、trim 済み body の 201 だけ実 Service が必要なら A を 1 本**。session を要さない create は fake Repository で実 Service を直接呼ぶ既存 unit があるので、API テストは B で 201/200/409/404/401/400/422 を固める。

確認する HTTP:

1. 未認証 POST/GET/PATCH/DELETE → 401 `unauthorized`
2. 正常作成 → 201、`Location`、`data.status === "pending"`、`rawText` が trim 済み（実 Service を使う場合）
3. 同一 key・同一 body 再 POST → 200、同じ `id`（fake の `created=False` で可）
4. 同一 key・異なる本文 → 409 `idempotency-key-conflict`
5. `Idempotency-Key` なし → 400 `idempotency-key-required`
6. `rawText` 空（JSON `""`）→ 422。空白のみは Service 経由なら `validation-error` かつ `/rawText`
7. 自分の GET → 200
8. 他人の ID で GET/PATCH/DELETE → 404 `capture-not-found`
9. 存在しない ID → 404
10. 一覧に他人の行が混ざらない（fake が query.user_id を使うことを assert）
11. DELETE 後 GET → 404
12. 不正 cursor → 400 `malformed-cursor`

JWKS 障害の 500 は既存 verifier 契約を流用。このファイルで増やさなくてよい。

既存の `test_capture_service.py` / `test_api.py` / `test_capture_repository.py` は壊さない。

## 実装順

1. failing `test_capture_api.py`（router が無いところで 404）
2. `ApiResponseWithMeta` / `CursorMeta` / `problem_responses` 400・409
3. `schemas.py` と `get_capture_service`
4. `router.py` を `create_app` に載せる。CORS
5. `CaptureTextInvalidError` の `errors[]`
6. テスト GREEN
7. OpenAPI export と client 生成



## 次ステップ（Web）

方針は [20-week3-capture-web.md](./20-week3-capture-web.md)。`/captures` と detail。生成 client の `createCapture` 等を使う。Idempotency-Key は Client Component が投稿意図ごとに発行する。

## 関連

- [Capture 契約](./13-week3-capture-contract.md)
- [Capture Service](./18-week3-capture-service.md)
- [エラーハンドリング](./04-error-handling.md)
- [API・データ契約](./06-api-data-contracts.md)
- [命名規約](./03-naming-conventions.md)
- [プロジェクト構成](./02-project-structure.md)
- [Week 2 認証失敗契約](./12-week2-auth-failure-contract.md)

