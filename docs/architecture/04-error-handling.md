# エラーハンドリング方針

## 目的

利用者には回復方法を、クライアントには安定した識別子を、運用者には追跡可能な情報を提供します。内部例外、SQL、token、個人情報をレスポンスへ漏らしません。

## エラー分類

### 想定内エラー

通常の業務フローで発生し得る状態です。

- 入力検証失敗
- 未認証・権限不足
- リソース不存在
- 状態競合
- レート制限
- 冪等キーの不整合
- AI処理のタイムアウトまたは処理不能

型付きのアプリケーション例外として表現し、API境界でHTTPへ変換します。

### 想定外エラー

バグ、設定不備、DB障害など、通常フローとして扱えない例外です。

- アプリケーション層では握り潰さない
- 最上位ハンドラーで記録し、汎用500レスポンスへ変換する
- Sentryへ送信する
- 利用者にスタックトレースや内部メッセージを返さない

## APIエラー形式

RFC 9457 Problem Detailsに準拠し、Content-Typeは`application/problem+json`とします。
正常レスポンスの`data`エンベロープでは包みません。

```json
{
  "type": "https://api.hibi.example/problems/capture-not-found",
  "title": "Capture not found",
  "status": 404,
  "detail": "The requested capture does not exist.",
  "instance": "/api/v1/captures/019...",
  "requestId": "019..."
}
```

規則:

- `type`: 問題タイプの安定した絶対URI。クライアントの分岐に使用する
- `title`: 問題タイプごとに固定する
- `status`: HTTP statusと一致させる
- `detail`: 当該発生に固有な人間向け説明。機械判定に使用しない
- `instance`: 発生したリクエストまたは問題インスタンスのURI
- `requestId`: ログ・trace・Sentryと共通の追跡ID

入力エラーには拡張メンバー`errors`を使用します。

```json
{
  "type": "https://api.hibi.example/problems/validation-error",
  "title": "Request validation failed",
  "status": 422,
  "detail": "One or more fields are invalid.",
  "requestId": "019...",
  "errors": [
    {
      "pointer": "/rawText",
      "code": "too_long",
      "detail": "Must contain at most 2000 characters."
    }
  ]
}
```

BEでは共通Pydantic modelとして定義し、任意の`dict`を組み立てません。

```python
from pydantic import BaseModel


class FieldProblem(BaseModel):
    pointer: str
    code: str
    detail: str


class ProblemDetails(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str
    errors: list[FieldProblem] | None = None
```

JSONでは共通alias設定により`request_id`を`requestId`として返します。

## HTTP status

- `400`: JSONとしては妥当だが、リクエスト全体の意味が不正
- `401`: tokenなし、期限切れ、検証失敗
- `403`: 認証済みだが操作権限なし
- `404`: リソース不存在。別ユーザー所有リソースも原則404にして存在を秘匿
- `409`: 現在状態との競合、冪等キーとpayloadの不一致
- `422`: field validation失敗
- `429`: レート制限。`Retry-After`を付与
- `500`: 想定外の内部エラー
- `502`: 同期処理に必要な外部サービスの不正応答
- `503`: 一時的に処理不能。必要に応じ`Retry-After`
- `504`: 同期外部処理のタイムアウト

## FastAPI

- 業務層で`HTTPException`をraiseしない
- 業務例外からProblem Detailsへの変換はGlobal Exception Handlerへ集約する
- `RequestValidationError`、Starlette `HTTPException`、未処理例外を共通形式へ正規化する
- 例外ハンドラーは元例外を保持してログへ渡す
- DB transactionは例外時にrollbackする
- Repositoryは「0件」を例外にするか`None`にするかをメソッド契約で明示する

```python
class CaptureNotFoundError(Exception):
    def __init__(self, capture_id: UUID) -> None:
        self.capture_id = capture_id
        super().__init__("capture not found")
```

例外メッセージをAPI契約として使用しません。

## Global Exception Handler

HTTP APIの例外変換はGlobal Exception Handlerへ統一します。
Routerごとに同じ`try/except`を書きません。

```text
Repository
  -> Application Service
    -> typed application/domain exception
      -> Global Exception Handler
        -> RFC 9457 Problem Details
```

### 責務

- Repository: 永続化を行い、HTTP statusを知らない
- Application Service: 業務上の失敗を型付き例外としてraiseする
- Router: 入力をユースケースへ渡し、正常レスポンスを組み立てる
- Global Exception Handler: 例外をHTTP statusとProblem Detailsへ変換する
- 最終Handler: 未知の例外を記録し、安全な500レスポンスへ変換する

### 登録

例外処理は`register_exception_handlers`へ集約し、application生成時に
一度だけ登録します。

```python
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        ApplicationError,
        handle_application_error,
    )
    app.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,
    )
    app.add_exception_handler(
        StarletteHTTPException,
        handle_http_exception,
    )
    app.add_exception_handler(
        Exception,
        handle_unexpected_exception,
    )
```

Handlerは役割ごとに分けます。すべての分岐を1つの巨大な関数へ
集約しません。

```text
ApplicationError
  -> 定義済みtype/statusのProblem Details

RequestValidationError
  -> 422 validation-error + errors[]

StarletteHTTPException
  -> framework由来の404等を共通形式へ正規化

Exception
  -> log/Sentry + 内部情報を含まない500
```

### マッピング規則

- 業務例外型とProblem `type`/statusの対応を一か所で管理する
- `str(exception)`をそのまま`detail`へ設定しない
- 未登録の`ApplicationError`は安全側に倒して500とし、監視へ送る
- `requestId`をresponse、構造化ログ、Sentryへ共通で設定する
- 既に記録済みの同一例外を各層で重複記録しない
- 別ユーザー所有resourceの不存在と権限不足は情報漏洩を避けて404へ統一する

### Transaction

Global Exception HandlerはDB rollbackの責務を持ちません。
rollbackはsession dependencyまたはUnit of Workのcontext managerで保証します。
Handlerはtransaction終了後の例外をHTTPへ変換します。

### Worker

Global Exception HandlerはHTTP requestだけが対象です。arq Workerは
Job実行境界で別の共通処理を持ちます。

- retry可能性を判定する
- retry回数と最終失敗を記録する
- 構造化ログとSentryへ送る
- 上限到達後にfailed状態へ遷移する
- HTTPレスポンスは生成しない

## Next.js / React

### Server Component・route segment

- 期待されるエラーは戻り値として扱い、画面内で説明する
- 予期しない例外は最寄りの`error.tsx`で受ける
- root layoutを越える例外は`global-error.tsx`で受ける
- 存在しないresourceは`notFound()`と`not-found.tsx`を使う
- ローディングは`loading.tsx`またはSuspenseで表現する

### Client Component

- APIクライアントでProblem Detailsを型付き`ApiProblem`へ変換する
- 通信・中断・不正responseを含む`ApiClientError`へ正規化する
- 想定内エラーは`ApiResult<T>`の`ok: false`として扱う
- 分岐は`type`または`status`で行い、`detail`文字列を解析しない
- field errorは対応する入力欄へ表示する
- 回復可能な通信エラーには明示的な再試行ボタンを出す
- event handler内の例外は自動でError Boundaryへ届かないため、catchして状態更新する
- toastだけで重要エラーを表現せず、操作箇所の近くに永続表示する

`ApiResult`、`ApiProblem`、正常レスポンスの型定義は
[API・データ契約](./06-api-data-contracts.md)を正とします。

## リトライ

自動リトライ可能:

- 接続リセット
- timeout
- `429`
- 一部の`502`、`503`、`504`
- DB serialization/deadlock

自動リトライ禁止:

- validation error
- authentication/authorization error
- 意味的な`409`
- providerが明示した恒久エラー

規則:

- exponential backoff + jitterを使用する
- 上限回数と総時間を設定する
- 副作用を伴う操作は冪等キーがある場合だけ再試行する
- API、Worker、SDKの複数層で重複リトライしない
- 最終失敗を永続化し、手動再実行経路を用意する

## AI処理

- timeout、rate limit、invalid output、content policy、provider unavailableを区別する
- structured outputはPydanticで検証する
- 検証失敗を無制限に再生成しない
- Jev/LLM障害を「低confidence」と同一視しない
- user向けには処理状態と回復方法を返し、provider名・prompt・内部出力を露出しない
- user入力、生成全文、tokenを通常ログへ記録しない

## ログ

エラーログには次を含めます。

```text
event
requestId
traceId
userId（必要時。生メールアドレス等は避ける）
route / jobName
errorType
retryCount
durationMs
```

同一例外を各レイヤーで重複記録しません。追加情報を付与して再raiseし、最上位境界で一度記録します。
