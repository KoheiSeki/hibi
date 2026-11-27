# FE/BE 命名規約

## 共通原則

- 名前は実装方法ではなく業務上の意味を表す
- 同じ概念には全レイヤーで同じ語彙を使う
- 不要な略語、型を表す接頭辞、`data`・`info`・`manager`等の曖昧語を避ける
- 真偽値は疑問として読める名前にする
- 単位を省略しない
- 列挙値は永続的な機械識別子とし、表示文言から分離する

推奨:

```text
isArchived
hasReminder
timeoutSeconds
elapsedMs
captureId
```

避ける:

```text
flag
statusInfo
timeout
captureID
dataManager
```

## TypeScript / React

- 変数・関数・hook・プロパティ: `camelCase`
- Component・型・interface・enum相当: `PascalCase`
- 不変のモジュール定数: `UPPER_SNAKE_CASE`
- ファイル・フォルダ: `kebab-case`
- React componentファイル: `kebab-case.tsx`
- hook: `use`で始める
- event handler: Component内は`handleXxx`、propsは`onXxx`
- Context: `XxxContext`、Provider: `XxxProvider`

```typescript
const MAX_CAPTURE_LENGTH = 2_000;

type CaptureStatus = "pending" | "processing" | "completed" | "failed";

function useCaptureStatus(captureId: string) {}

function CaptureForm({ onSubmit }: CaptureFormProps) {
  const handleSubmit = () => {};
}
```

`IUser`、`TUser`等の接頭辞は使用しません。型は用途で命名します。

```typescript
type Capture = {};
type CreateCaptureInput = {};
type CaptureListItem = {};
```

## Python

PEP 8を基準にします。

- 変数・関数・module・package: `snake_case`
- class・Pydantic model・例外: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- 非公開メンバー: `_leading_underscore`
- Protocol: 能力を表す名詞、または`XxxPort`
- 例外: `Error`で終える

```python
MAX_CAPTURE_LENGTH = 2_000

class CaptureNotFoundError(Exception):
    pass

async def process_capture(capture_id: UUID) -> Capture:
    ...
```

`get_`は単一取得、`list_`は複数取得、`create_`は新規作成として
意味を固定します。`save_`のようにinsert/updateの区別が曖昧な名前は、
明確なupsert要件がある場合を除いて使用しません。

## FEのレイヤー別メソッド名

### Page / Component

- React Component: 業務名詞を`PascalCase`で表す
- 内部event handler: `handle<イベント>`
- props callback: `on<イベント>`
- boolean判定: `is`、`has`、`can`、`should`

```typescript
function CaptureForm({ onSubmit }: CaptureFormProps) {
  const handleSubmit = () => {};
}

const isProcessing = capture.status === "processing";
const canRetry = capture.status === "failed";
```

`doSubmit`、`clickHandler`、`processData`等、目的を説明しない名前は禁止します。

### Hook

- hookは必ず`use`で始める
- 単一取得: `use<Resource>`
- 一覧取得: `use<Resources>`
- mutation: `use<Create|Update|Delete><Resource>`
- UI状態: `use<目的>`

```text
useCapture
useCaptures
useCreateCapture
useUpdateCapture
useCaptureComposer
```

`useGetCapture`は`useCapture`と意味が重複するため使用しません。

### API client / Gateway

OpenAPIの`operationId`と同じ語彙を使用します。

- 単一取得: `get<Resource>`
- 一覧取得: `list<Resources>`
- 作成: `create<Resource>`
- 全置換: `replace<Resource>`
- 部分更新: `update<Resource>`
- 削除: `delete<Resource>`
- 非CRUD command: `<業務動詞><Resource>`

```text
getCapture
listCaptures
createCapture
updateCapture
deleteCapture
retryCapture
```

`fetch`はHTTP transportを直接扱う低レベル関数だけに許可します。
Feature層は`get`/`list`等の契約名を使用します。

### Server Action

Server Actionを使用する場合、公開関数は`<業務動詞><対象>Action`とします。
ただし、業務処理はFastAPIへ委譲します。

```text
createCaptureAction
signOutAction
```

### 変換・検証

- 値を別表現へ変換: `to<Target>`、`from<Source>`、`map<Source>To<Target>`
- schema検証と変換: `parse<Subject>`
- 検証結果だけを返す: `validate<Subject>`
- 文字列化/復元: `serialize<Subject>`、`deserialize<Subject>`
- collectionからの導出: `select<Subject>`

```text
mapCaptureResponseToViewModel
parseCreateCaptureForm
serializeCaptureDraft
selectPendingCaptures
```

## BEのレイヤー別メソッド名

### Router / Controller

URLはREST原則に従って名詞で表し、Pythonのendpoint関数はHTTP操作の
意味を示します。

- `GET /resources`: `list_resources`
- `GET /resources/{id}`: `get_resource`
- `POST /resources`: `create_resource`
- `PUT /resources/{id}`: `replace_resource`
- `PATCH /resources/{id}`: `update_resource`
- `DELETE /resources/{id}`: `delete_resource`
- 非CRUD command: `retry_resource`等の業務動詞

```python
@router.get("/captures/{captureId}", operation_id="getCapture")
async def get_capture(...) -> ApiResponse[CaptureResponse]:
    ...
```

`post_capture`や`capture_controller`のようにHTTP method名または層名を
そのまま関数名にはしません。

### Application Service / Use Case

CRUDそのものなら次を使用します。

```text
get_capture
list_captures
create_capture
update_capture
delete_capture
```

業務処理はCRUD名へ押し込めず、ユースケースを表す動詞を使用します。

```text
classify_capture
process_capture
schedule_reminder
generate_daily_briefing
retry_failed_capture
```

`handle`、`execute`、`process`は対象だけでは意味が確定しない場合に
乱用しません。

### Repository

Repositoryの公開methodは永続化方式ではなく、呼び出し側が必要とする
意味を表します。

- 単一取得: `get_by_<条件>`。存在しない場合は`None`
- 複数取得: `list_by_<条件>`または`list_for_<所有者>`
- 存在確認: `exists_by_<条件>`
- 新規作成: `create_<resource>`
- 更新: `update_<resource>`
- 削除: `delete_<resource>`
- 明示的upsert: `upsert_<resource>`

```text
get_by_id
list_for_user
exists_by_idempotency_key
create_capture
update_processing_result
delete_capture
```

`select_`/`insert_`はSQLという実装詳細を漏らすため、Repositoryの
公開methodには使用しません。SQL statementを組み立てる非公開helperや
query moduleに限り、次のprefixを許可します。

```text
select_pending_captures_stmt
insert_outbox_event_stmt
update_capture_status_stmt
delete_expired_events_stmt
```

`create_`と`insert_`、`update_`と`save_`を同じRepository内で
同義語として混在させません。

### Domain Policy

副作用のないルールは戻り値の意味に合わせます。

```text
calculate_urgency_score
decide_capture_route
validate_transition
can_retry_capture
is_capture_expired
```

### External Adapter

provider名ではなく能力を先に表します。

```text
classify_capture
generate_briefing
embed_texts
publish_event
upload_object
```

provider固有実装はclass名で区別します。

```text
JevClassifier
OpenAIGenerator
SupabaseObjectStorage
```

### Worker / Job

- arq entrypoint: `<業務動詞>_<対象>_job`
- 定期処理本体: `run_<処理名>`
- outbox配送: `relay_<対象>`

```text
process_capture_job
run_daily_digest
relay_outbox_events
```

## HTTP API

- Base path: `/api/v1`
- Resource path: 小文字・複数名詞・`kebab-case`
- 動詞をpathへ置かず、HTTP methodで表現する
- 標準CRUDで表現できないcommandだけ末尾に動詞を許可する
- query/path parameterとJSON fieldは`camelCase`
- Headerは標準名を優先し、独自名は意味を明確にする

```text
POST   /api/v1/captures
GET    /api/v1/captures/{captureId}
PATCH  /api/v1/captures/{captureId}
POST   /api/v1/captures/{captureId}/retry
GET    /api/v1/digest-reports?fromDate=2026-09-01
```

FastAPI内部では`snake_case`を使い、Pydantic aliasでJSONの`camelCase`へ変換します。手作業で辞書キーを変換しません。

## OpenAPI

- `operationId`を明示し、生成後に変わらない名前にする
- `<verb><Resource>`形式を基本とする
- request/response schemaは用途を表す接尾辞を使う

```text
createCapture
getCapture
listCaptures
retryCapture

CreateCaptureRequest
CaptureResponse
CaptureListResponse
```

## Request / Response型の接尾辞

API境界の型は省略形の`Req` / `Res`を使用せず、
**`Request` / `Response`へ統一**します。

理由:

- `Res`がresponse、resource、resultのどれか判別しづらい
- OpenAPIと生成TypeScript clientで意味が明確になる
- FE/BEで同じschema名を共有できる
- 検索時にAPI境界型を見つけやすい

### BE / Pydantic

- request body: `<Action><Resource>Request`
- 単一response data: `<Resource>Response`
- 一覧response data: `<Resource>ListResponse`
- command response: `<Action><Resource>Response`
- query parameter model: `<Action><Resource>Query`
- path parameter modelが必要な場合: `<Resource>PathParams`

```text
CreateCaptureRequest
UpdateCaptureRequest
CaptureResponse
CaptureListResponse
RetryCaptureResponse
ListCapturesQuery
CapturePathParams
```

共通エンベロープは`ApiResponse[T]`と
`ApiResponseWithMeta[T, TMeta]`を使用します。

```python
@router.post(
    "/captures",
    response_model=ApiResponse[CaptureResponse],
    operation_id="createCapture",
)
async def create_capture(
    request: CreateCaptureRequest,
) -> ApiResponse[CaptureResponse]:
    ...
```

### FE / TypeScript

OpenAPIから生成された`Request` / `Response`名をそのまま使用します。
FE都合の型は役割を明示します。

```text
CreateCaptureRequest
CaptureResponse
CaptureViewModel
CaptureFormValues
CaptureDraft
```

API responseを画面用に加工した型へ`Response`を付けません。
`ViewModel`、`FormValues`、`Draft`等、実際の役割を使用します。

### API境界外

Application層の入出力へ機械的に`Request` / `Response`を付けません。

- ユースケース入力: `<Action><Resource>Command`
- ユースケース結果: `<Action><Resource>Result`
- Domain entity/value object: 業務名詞
- Event: 過去形の業務事実 + `Event`
- Job引数: `<Action><Resource>JobArgs`

```text
CreateCaptureCommand
CreateCaptureResult
Capture
CaptureClassifiedEvent
ProcessCaptureJobArgs
```

これによりHTTP契約と内部ユースケース型を分離します。

### 禁止する混在

次の表記を同一コードベースで混在させません。

```text
CreateCaptureReq
CreateCaptureRequest
CaptureRes
CaptureResponse
CaptureDto
```

新規コードでは`Req`、`Res`、汎用的な`Dto`を使用しません。

## PostgreSQL

- schema・table・column・constraint・index: `snake_case`
- table: 複数名詞
- 主キー: `id`
- 外部キー: `<resource>_id`
- 時刻: `<event>_at`
- 日付: `<event>_date`
- 真偽値: `is_`または`has_`
- index: `ix_<table>__<columns>`
- unique constraint: `uq_<table>__<columns>`
- foreign key: `fk_<table>__<column>__<referenced_table>`
- check constraint: `ck_<table>__<rule>`

```text
captures
capture_items
user_id
created_at
processed_at
is_archived
ix_captures__user_id_created_at
```

## ID・日時・金額

- 公開IDとユーザーIDはUUIDを基本とする
- Supabase Authの`sub`はUUIDとして扱う
- 日時はUTCで保存し、APIではoffset付きRFC 3339文字列を返す
- ユーザーのtimezoneはIANA名（例: `Asia/Tokyo`）で保存する
- 金額は最小通貨単位の整数、またはPostgreSQL `numeric`を使用する
- 浮動小数点数を金額に使用しない

## AI関連

- provider名と業務概念を分離する
- `model`だけでなく用途を名前に含める
- prompt/question/model設定はversionを持つ

```text
routingDecision
urgencyScore
classificationConfidence
promptVersion
embeddingModel
embeddingDimensions
```

SDK固有の名前を業務schemaへ露出させません。
