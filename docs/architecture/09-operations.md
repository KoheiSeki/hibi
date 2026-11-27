# 運用・監視・依存更新

## 環境

環境は最低限次の3つに分離します。

- local: Supabase local、ローカルWeb/API/Worker
- preview/staging: PR確認、非本番データ
- production: 本番データ

Supabase project、DB、Storage、secret、OAuth callback URLを環境ごとに
分離します。PR Previewをproduction DBへ接続しません。

## デプロイ

### Web

- Vercel Git Integrationを使用する
- PRごとにPreviewを作る
- `main` mergeでproductionへ反映する
- monorepoのRoot Directoryを`apps/web`へ設定する
- build時とruntimeの環境変数を区別する

### API・Worker

- 同一Dockerfileから同一artifactを作る
- APIとWorkerは起動commandだけを変える
- Render Web ServiceとBackground Workerへ配備する
- Python patch versionを`.python-version`、Docker、CI、Renderで一致させる
- API deployとWorker deployのversionを追跡可能にする

### Migration

1. backup/復旧可能性を確認
2. additive migrationを適用
3. migration検証
4. API/Workerをデプロイ
5. Webをpromotion
6. metricsとerrorを確認

アプリ起動時に自動migrationを実行しません。複数instanceによる競合と、失敗時の影響範囲を避けるためです。

## Health check

- `/health/live`: processが応答可能か。外部依存を確認しない
- `/health/ready`: DB等、traffic受付に必要な依存を短いtimeoutで確認する
- 詳細な設定値、接続文字列、例外を返さない
- Workerはheartbeat、最終成功時刻、queue滞留で監視する

## 構造化ログ

JSONを標準出力へ出します。

最低限のfield:

```text
timestamp
level
event
service
environment
release
requestId
traceId
route or jobName
statusCode
durationMs
```

必要な場合だけ`userId`、`captureId`等の識別子を追加します。
token、Cookie、authorization header、user本文、AI prompt/response全文を
通常ログへ出しません。

## Trace・Error monitoring

- W3C Trace ContextをWebからAPI、Worker、外部APIへ伝播する
- SentryをWeb/API/Workerへ導入する
- releaseをgit commit SHAで統一する
- source mapを安全にuploadする
- 想定内4xxを例外として大量送信しない
- provider timeout、DB query、queue遅延をspanとして観測する

## Metrics・Alert

最低限:

- request rate、error rate、duration
- p50/p95/p99 latency
- DB connection使用数
- slow query
- queue depth、oldest job age
- job success/failure/retry
- outbox pending/failed
- Jev/LLM latency、error、fallback率
- token/credit/cost
- daily digest成功率

Alertは「ユーザー影響がある」「対応手順がある」ものに限定します。単発例外すべてを通知しません。

## Backup・復旧

- Supabaseのbackup/PITR設定をproduction要件に合わせる
- StorageとDBの復旧範囲が異なることを明記する
- 四半期ごとにrestore手順を検証する
- RPO/RTOをproduction公開前に定義する
- migration前に復旧点を確認する
- 退会・削除・retention方針をDB、Storage、embedding、ログへ一貫して適用する

## 障害対応runbook

最低限、次の手順を`docs/operations`へ用意します。

- Web/API/Worker rollback
- migration失敗
- Supabase/Jev/LLM停止
- queue滞留
- outbox failed再処理
- signing key/secret漏洩とrotation
- 認可漏れ・他ユーザーデータ露出
- DB restore
- 高額なAI利用の緊急停止

## 依存関係

- `pnpm-lock.yaml`と`uv.lock`をcommitする
- CI/productionではfrozen lockfileを使う
- Node・Python versionをfileとplatform設定で固定する
- RenovateまたはDependabotを週次実行する
- patch/minor更新とmajor更新を分ける
- major更新は一依存または密接な依存群ごとにPRを作る
- 自動mergeはCIを通過した低リスクな開発依存patchに限定する
- high/critical脆弱性は優先対応する
- Python 3.14対応wheel、DB driver、observability SDKをproduction前に確認する

「常にlatest」をversion指定に使いません。採用時の最新安定版をlockし、更新PRで意図的に追従します。

## コスト管理

- Vercel、Render、Supabase、Jev、LLMに月額予算とalertを設定する
- LLM呼び出し数・token・model別費用を計測する
- embeddingの重複生成を避ける
- 定型応答はtemplateを使用する
- AI処理へuser/日次の上限を設定する
- queue滞留による再試行stormを防ぐ

## 定期レビュー

月次:

- 依存更新
- error/latency/cost
- 未使用feature flag・環境変数
- failed job/outbox

四半期:

- restore訓練
- secret/key rotation確認
- threat model
- 権限・RLS
- ADRと実装の乖離
- データretention
