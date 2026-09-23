# アーキテクチャ方針

## 基本原則

Hibiはモジュラーモノリスとして開始します。コードとデータの境界を明確にしつつ、分散システム固有の運用コストは必要になるまで負いません。

- Next.jsはUI、レンダリング、Supabase Authセッションを担当する
- FastAPIは唯一の業務APIとして、認可、業務ロジック、DBアクセス、AIオーケストレーションを担当する
- WorkerはFastAPIと同じPythonパッケージのユースケースを呼び出し、業務ロジックを重複させない
- PostgreSQLを業務データの唯一の正とする
- 外部サービスはアダプター越しに利用し、SDK固有型を業務層へ漏らさない

## システム境界

```text
Browser
  |
  v
Next.js / Vercel
  - App Router
  - Server/Client Components
  - Supabase Auth session
  - generated API client
  |
  | HTTPS + Bearer access token + trace context
  v
FastAPI / Render
  - authentication and authorization
  - use cases and domain policy
  - Jev/LLM orchestration
  - OpenAPI
  |
  +--> Supabase PostgreSQL / pgvector
  +--> Supabase Storage
  +--> Redis-compatible queue
  +--> Jev / LLM / embedding providers

Render Worker
  - arq jobs
  - cron
  - transactional outbox relay
```

## デプロイ単位

デプロイ単位は3つですが、ソースは1つのモノレポで管理します。

1. `web`: VercelへデプロイするNext.jsアプリ
2. `api`: Render Web ServiceへデプロイするFastAPI
3. `worker`: APIと同じPythonイメージを別コマンドで起動するRender Background Worker

APIとWorkerを別リポジトリ・別Pythonパッケージに分けません。非同期化はデプロイ形態であり、ドメイン境界ではないためです。

## レイヤーと依存方向

FastAPI側の依存方向は次に固定します。

```text
HTTP router / arq task
        |
        v
application service / use case
        |
        v
domain policy and ports
        |
        v
repository / provider adapters
```

- RouterはHTTP変換・認証依存・ステータスコード選択だけを行う
- arq taskは引数を検証してユースケースを呼ぶだけにする
- Serviceはトランザクション境界とユースケースを表現する
- Repositoryは永続化を隠蔽するが、汎用CRUD抽象化を作りすぎない
- AdapterはSupabase、Jev、LLM等のSDKを隔離する
- 下位層からFastAPIやarqへ依存しない

Next.js側はルート単位のコロケーションを基本とし、共有が確認できたものだけを共通化します。

```text
route page/layout
      |
      v
feature component / action
      |
      v
generated API client wrapper
```

## Capture処理

1. Webが`Idempotency-Key`付きでCapture作成APIを呼ぶ
2. APIが生入力とoutboxイベントを同一トランザクションで保存する
3. APIは処理状態を含む`202 Accepted`を返す
4. Outbox relayがarqへジョブを投入する
5. WorkerがJevでカテゴリ、優先度、ルートを判定する
6. 決定論的ポリシーが実際の処理を選ぶ
7. 必要な場合だけLLM、Embedding、RAGを実行する
8. 結果、利用モデル、プロンプト/質問バージョンを保存する
9. Webは初期段階では短時間pollingで状態を更新する

SSEやRealtimeは、pollingの負荷またはUX上の問題を計測してから導入します。

## AIの責務分担

Jev:

- intent/categoryの分類
- urgency等のスコア
- confidenceを含むルーティング判断
- LLMを呼ぶ必要性の判定材料

LLM:

- 自然文の生成
- 長文要約
- 複雑な構造化抽出
- confidenceが低い場合の聞き返し文生成

決定論的コード:

- 認証・認可
- 入力制約
- データ所有権
- 削除・外部送信等の不可逆操作
- リトライ上限、レート制限、コスト上限

定型文で足りる確認メッセージにLLMを使いません。AI provider障害時に無条件で別providerへ切り替えず、ユースケースごとのポリシーに従います。

## 非同期処理

- API保存とジョブ投入の二重書き込みにはTransactional Outboxを使用する
- ジョブはat-least-once実行を前提に冪等にする
- 冪等キーはユースケースに応じて`resource_id + processing_version`等で構成する
- リトライ対象は一時障害だけとし、検証エラーや認可エラーは再試行しない
- リトライ上限後は失敗状態を永続化し、再実行可能な運用導線を設ける
- cronはarqに一本化し、Render Cronと二重実行しない

## データアクセス

- Web/Browserから業務テーブルを直接操作しない
- 業務テーブルはSupabase Data APIの公開対象外となるprivate schemaへ置く
- FastAPIは専用の最小権限DBロールを使う
- すべてのユーザー所有データに`user_id UUID`を持たせる
- Repositoryは必ず検証済みPrincipalの`user_id`を検索条件に含める
- Supabaseのsecret/service role keyを通常の業務APIで使用しない
- Storageへの大容量アップロードは、APIが検証後に発行する署名付きURLを使ってBrowserから直接送る

## 将来の分離条件

以下のいずれかが計測で確認された場合のみ、サービス分離を検討します。

- 特定モジュールだけ独立したスケールが必要
- デプロイ頻度や障害ドメインを分離する必要
- 別チームが独立して所有する
- データ整合性より可用性を優先する明確な要件

分離前に、モジュール境界・API契約・データ所有権をADRで確定します。
