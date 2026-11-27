# 現状アーキテクチャ(Week 10 時点)

Week 10 までに実装した Hibi の構成をまとめる。方針は [01-architecture.md](./01-architecture.md)、週ごとの詳細は各週の文書にある。この文書は「いま何が動いているか」の地図で、方針の正本ではない。図は `docs/architecture/hibi-architecture.pptx`(Keynote 版は `architecture.key`)と同じ内容。

## 全体像

モジュラーモノリス。デプロイ単位は web、api、worker の 3 つで、api と worker は同じ Python パッケージ(`hibi`)を別のコマンドで起動する。Week 11 でデプロイするまでは、すべてローカルで動かしている。

```text
Browser
  |
  v
Next.js (web, Vercel 予定)
  - App Router、Server Components / Server Actions
  - Supabase Auth セッション
  - 生成された API client (@hibi/api-client)
  |
  | HTTPS + Bearer (Supabase の JWT)
  v
FastAPI (api, Render Web Service 予定)          arq Worker (worker, Render Background Worker 予定)
  - Router / 認証依存 (JWKS で JWT 検証)          - relay_outbox_events   5 秒毎
  - Service: Capture, Digest, Profile            - process_capture_job
  - Policy: ルート判定、シナリオ提案、Today 優先度 - run_daily_digest      15 分毎
  - Repository / AI Adapter                      - generate_digest_report_job
  |                                              - recover_stalled_work  5 分毎
  |                                                |
  +-----------------+------------------------------+
                    |                |              |
                    v                v              v
   Supabase PostgreSQL + pgvector   Redis (arq)    AI (Jev、LLM、Embedding)
```

## 技術スタック

| 層 | 採用 |
| --- | --- |
| Web | Next.js 16 App Router、React 19、TypeScript strict、Tailwind、vitest、Testing Library |
| API / Worker | Python 3.14、FastAPI、SQLAlchemy 2 (async)、arq、structlog、pytest |
| データ | Supabase PostgreSQL、pgvector、Supabase Auth |
| キュー | Redis 互換 (arq) |
| AI | Jev (分類)、OpenAI 互換の LLM (聞き返し文、週次要約)、OpenAI 互換の Embedding |
| API 契約 | FastAPI の OpenAPI を正とし、`just openapi` で TypeScript client を生成 |

## API(`/api/v1`)

認証が要る endpoint は、Supabase の JWT を JWKS で検証し、`user_id` を必ず検索条件に含める。エラーは Problem Details で返す。

| リソース | endpoint | 用途 |
| --- | --- | --- |
| 基盤 | `GET /health`、`GET /me`、`POST /echo`、`GET /protected-resource` | 死活確認、認証の確認 |
| Capture | `POST /captures` | 記録の作成。`Idempotency-Key` 付き、`202 Accepted` |
| | `GET /captures`、`GET /captures/{id}` | 一覧(cursor)と単体取得(polling に使う) |
| | `PATCH /captures/{id}`、`DELETE /captures/{id}` | 本文の更新と削除 |
| | `POST /captures/{id}/retry` | `failed` の再実行 |
| | `POST /captures/{id}/scenario/accept` | 提案されたシナリオの確認 |
| | `POST` / `DELETE /captures/{id}/scenario/done` | 完了にする、未完了に戻す |
| | `GET /captures/today` | 今日やること(優先度順) |
| | `GET /captures/search` | キーワード検索と意味検索 |
| Digest | `GET /digest-reports` | ダイジェストの一覧(`kind`、`fromDate`、`limit`) |
| | `POST /digest-reports/{id}/retry` | `failed` の再生成。`202 Accepted` |

## Web の画面

| パス | 画面 |
| --- | --- |
| `/` | トップ |
| `/login` | ログイン |
| `/captures` | 記録の入力と一覧、検索 |
| `/captures/{captureId}` | 記録の詳細。聞き返し文、シナリオの確認と編集 |
| `/captures/today` | 今日やること。行ごとに完了にできる |
| `/captures/digest` | 朝のダイジェストと週次レビュー。`failed` はもう一度作れる |
| `/account` | アカウント |

Web は業務テーブルを直接読まない。Server Component と Server Action から、生成された client で API を呼ぶ。処理中の Capture とダイジェストは、3 秒おきの polling で画面に反映する。

## データ

業務データは PostgreSQL だけを正とする。詳細は [14-er.md](./14-er.md) と [15-table-catalog.md](./15-table-catalog.md)。

| テーブル | 中身 |
| --- | --- |
| `profiles` | ユーザーの timezone。「今日」と、ダイジェストを作る時刻の基準 |
| `captures` | 生の入力、処理状態 (`pending` → `processing` → `completed` / `failed`)、分類結果、聞き返し文 |
| `capture_scenarios` | 買い物、予定、支出のシナリオ。`proposed` → `accepted`、期限、完了 |
| `capture_embeddings` | 意味検索のための pgvector |
| `outbox_events` | job 投入を待つイベント (Transactional Outbox) |
| `digest_reports` | daily と weekly のダイジェスト。期間ごとに 1 行 (unique)、`pending` / `ready` / `failed` |

## Worker の job

| job | 起動 | 内容 |
| --- | --- | --- |
| `relay_outbox_events` | cron 5 秒毎 | 未送信の outbox を arq に投入する |
| `process_capture_job` | outbox から | Jev で分類 → policy で route → 必要なときだけ LLM の聞き返し文 → シナリオの提案 → embedding |
| `run_daily_digest` | cron 15 分毎 | timezone で朝 7 時を過ぎたユーザーの daily と、月曜の weekly の行を作り、outbox に積む |
| `generate_digest_report_job` | outbox から | daily は決定論的に集計する。weekly は集計に LLM の要約を足す |
| `recover_stalled_work` | cron 5 分毎 | 10 分以上 `processing` の Capture を `pending` に戻し、届いていない digest の予約を積み直す |

job は at-least-once で動く前提で、冪等にしている。一時的な障害だけを指数バックオフで再試行し、上限(3 回)を超えたら `failed` を保存して、画面から再実行できるようにしている。

## 主な処理の流れ

### Capture

1. Web が `Idempotency-Key` 付きで `POST /captures` を呼ぶ
2. API が Capture と outbox を同じ transaction で保存し、`202` を返す
3. relay が outbox を arq に投入する
4. Worker が分類、route、シナリオ、embedding を処理して結果を保存する
5. Web は、完了するまで単体取得を polling する

### ダイジェスト

1. `run_daily_digest` が、作る時刻を過ぎたユーザーの行を `pending` で作り、outbox に積む。unique 制約で、同じ期間の行は増えない
2. relay が `generate_digest_report_job` を投入する
3. Worker が中身を作って `ready` にする。失敗が続けば `failed`
4. Web の `/captures/digest` が最新の daily と weekly を 1 件ずつ読む。`pending` は polling し、`failed` は retry できる

## AI の扱い

AI は port (Protocol) の向こうに置き、SDK の型を業務層に出さない。API キーが無いときは fake の実装に切り替わるので、通常のテストと CI は外部 API を呼ばず、課金もない。

| 役割 | 本物 | キーが無いとき |
| --- | --- | --- |
| 分類 | Jev | `FakeCaptureClassifier` |
| 聞き返し文 | LLM | `FakeClarificationGenerator` |
| 週次要約 | LLM | `FakeReviewSummarizer` |
| Embedding | OpenAI 互換 API | `FakeTextEmbedder` |

LLM を呼ぶのは、route が `clarify` のときの聞き返し文と、週次要約だけ。不正な structured output は再試行せず、定型文で完了する。週次要約に渡すのは集計と完了したシナリオの title だけで、生の入力は送らない。

## まだ無いもの(Week 11 以降)

- 本番環境へのデプロイ (Vercel、Render)
- JSON 構造化ログの整備、request ID と trace ID の伝播、Sentry
- `/health/live` と `/health/ready`
- rate limit と AI コストの上限
- 通知 (Web Push、メール)
