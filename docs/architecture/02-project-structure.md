# プロジェクト構成

## 推奨ディレクトリ

```text
hibi/
├── apps/
│   ├── web/
│   │   ├── src/
│   │   │   ├── app/
│   │   │   │   ├── (public)/
│   │   │   │   ├── (authenticated)/
│   │   │   │   ├── auth/callback/route.ts
│   │   │   │   ├── error.tsx
│   │   │   │   ├── global-error.tsx
│   │   │   │   ├── loading.tsx
│   │   │   │   ├── not-found.tsx
│   │   │   │   └── layout.tsx
│   │   │   ├── components/ui/
│   │   │   ├── features/
│   │   │   └── lib/
│   │   │       ├── api/
│   │   │       ├── auth/
│   │   │       ├── env/
│   │   │       └── observability/
│   │   ├── public/
│   │   ├── tests/
│   │   ├── next.config.ts
│   │   ├── package.json
│   │   └── tsconfig.json
│   └── api/
│       ├── src/hibi/
│       │   ├── api/
│       │   │   ├── main.py
│       │   │   ├── dependencies.py
│       │   │   ├── exception_handlers.py
│       │   │   ├── problem_details.py
│       │   │   └── routers.py
│       │   ├── modules/
│       │   │   ├── captures/
│       │   │   ├── agenda/
│       │   │   ├── copilot/
│       │   │   ├── reviews/
│       │   │   └── profiles/
│       │   ├── ai/
│       │   ├── auth/
│       │   ├── core/
│       │   ├── db/
│       │   ├── jobs/
│       │   └── storage/
│       ├── tests/
│       │   ├── unit/
│       │   ├── integration/
│       │   ├── contract/
│       │   └── evals/
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── uv.lock
├── packages/
│   └── api-client/
│       ├── src/generated/
│       ├── openapi-ts.config.ts
│       ├── package.json
│       └── tsconfig.json
├── contracts/
│   └── openapi.json
├── supabase/
│   ├── migrations/
│   ├── tests/
│   ├── seed.sql
│   └── config.toml
├── docs/
│   ├── adr/
│   ├── ai/
│   ├── operations/
│   └── security/
├── .github/
│   ├── pull_request_template.md
│   └── workflows/
├── .env.example
├── .python-version
├── CONTRIBUTING.md
├── README.md
├── justfile
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
└── render.yaml
```

## Webの配置規則

### `app/`

Next.jsのルーティングと画面合成だけを置きます。

- `page.tsx`: データ取得の開始と画面合成
- `layout.tsx`: 共有レイアウト
- `loading.tsx`: Suspenseフォールバック
- `error.tsx`: ルートセグメントの予期しないエラー
- `global-error.tsx`: ルートレイアウトを越えたエラー
- `route.ts`: Supabase Auth callback等、Web固有のHTTP処理だけ

業務APIの代替となるRoute Handlerは作りません。

### `features/`

ユーザー機能単位でUI・hook・表示用型をまとめます。

```text
features/capture/
├── components/
├── hooks/
├── mappers/
├── capture-form.tsx
└── index.ts
```

Feature間の直接importは避け、共有が必要なら`components/ui`または`lib`へ小さな公開APIとして移します。

### `components/ui/`

業務知識を持たないUI部品だけを置きます。API呼び出し、認証判定、ドメイン名への依存は禁止します。

### `lib/`

- `api`: 生成クライアントへのtoken・request ID注入
- `auth`: Supabase browser/server client
- `env`: 環境変数の起動時検証
- `observability`: Sentry、trace、logger

`utils.ts`のような無制限の物置ファイルは作りません。

## APIの配置規則

### 業務モジュール

モジュールは技術レイヤー別の巨大フォルダではなく、変更理由が近いファイルをまとめます。

```text
modules/captures/
├── router.py
├── schemas.py
├── service.py
├── repository.py
├── models.py
├── errors.py
└── policies.py
```

- `router.py`: HTTP変換
- `schemas.py`: 外部I/OのPydanticモデル
- `service.py`: ユースケースとトランザクション
- `repository.py`: モジュール固有の永続化
- `models.py`: SQLAlchemyモデル
- `errors.py`: ドメイン/アプリケーション例外
- `policies.py`: 副作用のない決定ロジック

小さいモジュールでは不要なファイルを先に作りません。1ファイルが複数の変更理由を持ち始めた時点で分割します。

### 共通パッケージ

- `api`: FastAPI app、router集約、依存、Global Exception Handler
- `ai`: provider非依存port、Jev/LLM/Embedding adapter、routing policy
- `auth`: Supabase JWT検証、Principal
- `core`: 設定、ログ、telemetry、idempotency
- `db`: engine/session、Unit of Work、DB共通型
- `jobs`: arq entrypoint、task、cron、outbox relay
- `storage`: Storage portとSupabase adapter

`core`へ業務ロジックを置きません。

Global Exception Handlerは`api/exception_handlers.py`へ集約し、
RFC 9457の共通型は`api/problem_details.py`へ置きます。
業務モジュールはHTTP response形式を知りません。

## 依存管理

- JavaScript/TypeScriptはpnpm workspaceを使用する
- Pythonはuvと`uv.lock`を使用する
- lockfileを必ずコミットする
- Turborepo/Nxは、CI時間が問題になるまで導入しない
- 共通コマンドは`justfile`にまとめ、package managerを隠蔽しすぎない
- OpenAPI生成物は`packages/api-client/src/generated`以外に置かない

## Supabaseスキーマ管理

- `supabase/migrations`を唯一のDBスキーマ履歴とする
- Alembicとの二重管理は禁止する
- migrationはロールフォワードを基本とする
- seedはテスト・ローカル開発用データだけを持つ
- RLS/権限テストを`supabase/tests`へ置く
- table または主要な FK を追加・変更したら、同じ PR で [ER図](./14-er.md) と [テーブル定義](./15-table-catalog.md) を更新する

## ファイルサイズの目安

行数だけでは分割しません。ただし、次の状態は分割のシグナルです。

- 1ファイルに複数の公開責務がある
- テストで無関係な依存を多数mockする必要がある
- import時に循環依存が起きる
- 変更のたびに同じ巨大ファイルで競合する
- 名前で責務を説明できない
