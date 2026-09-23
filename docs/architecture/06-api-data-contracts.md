# API・データ契約

## Single Source of Truth

FastAPIが生成するOpenAPIをAPI契約の唯一の正とします。

- FastAPIのPydantic schemaからOpenAPIを生成する
- `contracts/openapi.json`へ正規化して保存する
- OpenAPIからTypeScript型とfetch clientを生成する
- 手書きの重複型を作らない
- 生成ファイルを手編集しない
- API変更と生成client更新を同じPRに含める
- CIで再生成し、差分があれば失敗させる

生成toolは採用時点で保守されているものをversion固定します。第一候補は`@hey-api/openapi-ts`です。

## API設計

- JSON APIは`/api/v1`配下に置く
- resource指向のpathを使用する
- request/response schemaを分離し、末尾を`Request` / `Response`に統一する
- database modelをそのままresponseにしない
- collection responseは将来のpaginationを考慮してobjectで包む
- mutationには適切なidempotency設計を持たせる
- `operationId`を明示する

`Req` / `Res` / `Dto`は使用しません。API境界外のユースケース型には
`Command` / `Result`を使用します。詳細は
[FE/BE命名規約](./03-naming-conventions.md)に従います。

## BEの正常レスポンス

JSONを返す成功レスポンスは、必ず`data`で包みます。

### 単一resource

```json
{
  "data": {
    "id": "019...",
    "rawText": "牛乳を買う",
    "status": "processing",
    "createdAt": "2026-09-23T14:00:00Z"
  }
}
```

### Collection

一覧も`data`を配列とし、pagination等の付加情報だけを`meta`へ置きます。

```json
{
  "data": [
    {
      "id": "019...",
      "rawText": "牛乳を買う",
      "status": "completed",
      "createdAt": "2026-09-23T14:00:00Z"
    }
  ],
  "meta": {
    "nextCursor": "019...",
    "hasNextPage": true
  }
}
```

### Mutation

- `201 Created`: 作成されたresourceを`data`で返し、`Location`も付与する
- `202 Accepted`: job/resource IDと処理状態を`data`で返す
- `204 No Content`: bodyを返さない
- `DELETE`: 削除結果をクライアントが必要としなければ`204`を使用する

```json
{
  "data": {
    "id": "019...",
    "status": "pending"
  }
}
```

成功レスポンスに`success: true`、HTTP status、汎用`message`を重複して
含めません。表示文言はFEが決定します。

### BEの型

Pydanticの共通型でresponse schemaを明示します。

```python
from typing import Generic, TypeVar

from pydantic import BaseModel

DataT = TypeVar("DataT")
MetaT = TypeVar("MetaT")


class ApiResponse(BaseModel, Generic[DataT]):
    data: DataT


class ApiResponseWithMeta(BaseModel, Generic[DataT, MetaT]):
    data: DataT
    meta: MetaT


class CursorMeta(BaseModel):
    next_cursor: str | None
    has_next_page: bool
```

Python内部は`snake_case`、JSON/OpenAPIはalias generatorで`camelCase`へ
変換します。Routerから任意の`dict`を返さず、`response_model`と戻り値型を
指定します。

### エンベロープの例外

以下は`data`で包みません。

- `204 No Content`
- file download
- streaming response / SSE
- redirect
- provider仕様に従うWebhook response
- RFC 9457 Problem Details

## BEのエラーレスポンス

エラーは`{"error": {...}}`で包まず、RFC 9457のfieldをtop-levelへ
配置します。Content-Typeは`application/problem+json`です。

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

`type`を機械判定に使用し、`detail`文字列では分岐しません。validation
errorの拡張形式は[エラーハンドリング方針](./04-error-handling.md)に
従います。

## FEの型定義

Wire formatとFE内部の制御型を分けます。

### Wire format

BEの正常レスポンスと1対1に対応します。

```typescript
export type ApiResponse<T> = {
  data: T;
};

export type ApiResponseWithMeta<T, TMeta> = {
  data: T;
  meta: TMeta;
};

export type CursorMeta = {
  nextCursor: string | null;
  hasNextPage: boolean;
};

export type FieldProblem = {
  pointer: string;
  code: string;
  detail: string;
};

export type ApiProblem = {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  requestId: string;
  errors?: FieldProblem[];
};
```

これらは原則としてOpenAPIから生成します。手書きする場合も生成型と
同名の重複型を作りません。

### FE内部の処理結果

HTTPエラーだけでなく、通信失敗・中断・契約不一致も表現できる
discriminated unionを使用します。

```typescript
export type ApiClientError =
  | { kind: "problem"; problem: ApiProblem }
  | { kind: "network"; message: string }
  | { kind: "aborted" }
  | { kind: "invalid-response"; message: string };

export type ApiResult<T, TMeta = never> =
  | {
      ok: true;
      data: T;
      meta?: TMeta;
    }
  | {
      ok: false;
      error: ApiClientError;
    };
```

規則:

- `ok`でnarrowingし、type assertionで成功扱いしない
- HTTP Problem Detailsは`kind: "problem"`へ正規化する
- `problem.type`または`problem.status`で分岐する
- network errorを架空のHTTP status `0`として表現しない
- `AbortError`は失敗通知対象と区別する
- invalid JSON/schemaは`invalid-response`として監視へ送る
- Server Componentの予期しないエラーは`ApiResult`へ握り潰さずthrowする
- validation等の想定内エラーは`ApiResult`で画面へ返す

`ApiResult<T> = { data: T }`だけでは成功・失敗を型で判別できないため、
`{ data: T }`はwire formatの`ApiResponse<T>`、FE内部の処理結果は
上記`ApiResult<T>`として役割を分離します。

## JSON規約

- field名は`camelCase`
- 日時はUTCのRFC 3339
- IDは文字列UUID
- nullとfield欠落を区別する
- enum値は小文字の安定識別子
- 金額は通貨codeと最小通貨単位を明示する
- paginationはcursor方式を基本とする

```json
{
  "id": "019...",
  "createdAt": "2026-09-23T14:00:00Z",
  "status": "processing",
  "amountMinor": 1280,
  "currency": "JPY"
}
```

## 互換性

非破壊変更:

- optional fieldの追加
- 新endpointの追加
- enumを受信側が未知値へ安全に対応できる場合の値追加

破壊的変更:

- required fieldの追加
- field削除・rename・型変更
- enum値の削除
- status codeまたは意味の変更
- pagination/orderの意味変更

破壊的変更が必要な場合は、移行期間を設けるか`/api/v2`を追加します。内部clientしか存在しない場合でも、Web/APIの独立デプロイ中に新旧versionが混在することを考慮します。

## Idempotency

作成・外部送信・AI処理開始など、再送され得るmutationは`Idempotency-Key`を受け付けます。

- keyはユーザーとoperation単位で一意にする
- request payloadのhashを保存する
- 同じkey・同じpayloadには最初の結果を返す
- 同じkey・異なるpayloadには`409`を返す
- retention期間を定義する
- Worker側もresource IDとprocessing versionで冪等化する

## DB型

- Auth user ID: UUID
- 公開resource ID: UUID
- 内部連番が必要ならDB内部だけに限定する
- timestamp: timezone付き
- date: 日付のみの業務概念に限定
- 金額: integerまたはnumeric
- JSONB: schemaが不定なprovider応答・metadataに限定
- enum: 変更頻度が高い場合はDB enumよりcheck constraintまたは参照tableを検討する

## PostgreSQL schema

- Supabase `auth` schemaは認証providerが管理する
- Hibi業務tableはData APIへ露出しないprivate schemaに置く
- runtime role、migration role、管理roleを分離する
- すべての外部キー列へ用途に応じたindexを付ける
- 一覧・outbox・cron等の主要queryに複合/部分indexを設計する
- indexは実queryと`EXPLAIN (ANALYZE, BUFFERS)`に基づいて追加する
- migrationは`supabase/migrations`だけで管理する

## pgvector

- embedding本文とembeddingをユーザー所有resourceへ紐付ける
- `embedding_model`、`embedding_dimensions`、`embedding_version`を保存する
- 検索時に必ずuser/tenant条件を含める
- distance metricをmodel仕様と一致させる
- データ量に応じてHNSW等のindexを導入し、計測前に過剰最適化しない
- embedding model変更時は新旧versionを共存させてbackfillする

## AI契約

provider SDK型を業務schemaとして使用しません。portは用途の型を返します。

```python
class RoutingDecision(BaseModel):
    route: CaptureRoute
    category: CaptureCategory
    urgency_score: float
    confidence: float
    policy_version: str
```

保存対象:

- provider/model識別子
- prompt/question/policy version
- latency
- token/credit usage
- validation結果
- fallback有無

生のchain-of-thoughtを要求・保存しません。provider応答全文の保存は目的・retention・アクセス権を定義した場合だけ許可します。
