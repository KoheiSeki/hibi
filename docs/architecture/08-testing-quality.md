# テスト・品質管理方針

## 基本原則

- 振る舞いをテストし、内部実装へ過度に結合しない
- バグ修正では先に再現テストを追加する
- 外部サービスを呼ばずに大部分のテストを実行可能にする
- coverage率だけを品質指標にしない
- 認証、認可、RLS、migration、冪等性、AI fallbackを重点的に検証する

## テストレイヤー

### Unit

対象:

- 決定論的なdomain policy
- Jev/LLM routing policy
- mapper・validator
- Pydantic schema
- React componentとhook
- エラー変換

DB、network、時刻、乱数は境界で注入します。SDK全体をmockせず、自分たちが定義したportをfakeにします。

### Integration

対象:

- FastAPI endpoint + 実PostgreSQL
- SQLAlchemy repository
- transaction/outbox
- Supabase JWT検証
- OpenAPI client
- arq taskと冪等性
- Storage/Jev/LLM adapterのsandboxまたは契約fake

SQLiteでPostgreSQL固有機能を代替しません。TestcontainersまたはSupabase local developmentを使用します。

### Contract

- FastAPI OpenAPI snapshot
- TypeScript client再生成差分
- Problem Details形式
- provider adapterの入出力schema
- webhook payload/署名

`operationId`、必須field、enum、status codeの意図しない変更を検知します。

### E2E

Playwrightで重要な利用者経路だけを検証します。

- signup/login/logout
- Capture作成から処理完了まで
- 今日の優先項目表示
- 別ユーザーresourceへのアクセス拒否
- AI provider障害時の回復UI
- mobile viewportでの主要操作

E2Eですべての組み合わせを網羅しません。

### AI evaluation

通常のpytestとは別に評価suiteを持ちます。

- 代表的な日常入力をversion管理する
- route/category/urgencyの期待値を保存する
- confidence閾値とfallback率を計測する
- precision/recall、latency、costを比較する
- prompt/question/model変更時に回帰評価する
- 本番user入力を無断でfixtureへコピーしない

評価は完全一致だけでなく、用途に適したmetricと人手reviewを併用します。

## FE品質

- TypeScript `strict`を有効にする
- `any`は境界での一時的利用を除き禁止する
- Server Componentをdefaultとし、対話性が必要な最小範囲だけ`"use client"`にする
- 非同期処理のwaterfallを避け、独立処理は並列化する
- 大きなclient dependencyはdynamic importを検討する
- accessibilityをlintとcomponent testで確認する
- button、form、dialogはkeyboard操作可能にする
- loading、empty、error、disabled状態を必ず設計する

実行項目:

```text
format
lint
typecheck
unit/component test
production build
Playwright
```

## BE品質

- Python 3.14の型構文を使用する
- Ruffでformatとlintを統一する
- public function、service、portに型注釈を付ける
- `Any`を外部境界以外へ伝播させない
- Pydanticで外部入力を検証する
- timezone-aware datetimeだけを使用する
- network/DB I/Oにはtimeoutを設定する
- async関数内で同期I/Oを実行しない

実行項目:

```text
ruff format --check
ruff check
type check
pytest
OpenAPI generation
Docker build
```

## DB・セキュリティテスト

最低限次の主体を検証します。

- 未認証
- 所有者
- 別ユーザー
- 管理権限保持者
- runtime DB role

検証内容:

- 読み取り・作成・更新・削除の許可/拒否
- user IDの付替え防止
- private schemaへのData APIアクセス拒否
- migrationを空DBへ適用可能
- production相当schemaから次migrationへ更新可能
- rollbackではなくロールフォワード修正が可能

## Test data

- factoryを使用し、fixture間の暗黙依存を避ける
- UUID・時刻を固定できるようにする
- testごとにデータを分離する
- production DBをtest/previewから参照しない
- snapshotにsecret・PIIを含めない

## CIの失敗基準

- lint/type/test/buildの失敗
- OpenAPIまたは生成clientの未commit差分
- migrationの適用失敗
- RLS/認可testの失敗
- high/critical脆弱性
- secret検出
- 主要E2E失敗

flaky testは単に再実行で隠さず、所有issueと期限を付けて隔離します。
