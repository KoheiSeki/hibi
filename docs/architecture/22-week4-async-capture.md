# Week 4: Capture の非同期処理

[実装スケジュール](./11-implementation-schedule.md) の Week 4。[Capture 処理](./01-architecture.md#capture処理) の 2〜4 と 9 を、AI なしで通す。Jev / LLM は Week 5 以降。見た目は [Capture 画面の見た目](./21-capture-visual.md)。

## このステップのゴール

Capture の保存と「処理を始める」記録を、同じ transaction で残す。API は待たずに `202 Accepted` を返す。別プロセスの Worker が状態を `pending` から `completed` または `failed` へ進める。画面は短い間隔で単体取得を繰り返し、糸の上で処理中だと分かる。

完了条件:

- 作成 API が `202 Accepted` を返す。body は今までどおり `ApiResponse[CaptureResponse]`
- Worker 完了まで `GET /api/v1/captures/{captureId}` で状態を追える
- 同じ job を二度実行しても、結果が二重にならない
- 一時障害は retry し、上限のあと `failed` になる
- 検証エラーと認可エラーは retry しない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| Jev / LLM / Embedding | Week 5 以降。Worker は状態遷移だけ |
| SSE / Realtime | polling の負荷を測ってから |
| カテゴリ、緊急度、route の表示 | 判定結果がまだない |
| status バッジ、色分け、番号 | [21](./21-capture-visual.md)。処理中は節の動きと短い文言 |
| Render Cron と arq cron の併用 | cron は arq に一本化する |
| Alembic | migration は `supabase/migrations` だけ |

## 状態

Week 3 で空けてある値を、この週から遷移させる。

```text
pending → processing → completed
                    └→ failed
```

- 作成直後は `pending`。outbox 行も同じ transaction で 1 件
- relay が job を投入し、Worker 開始で `processing`
- 正常終了で `completed`
- 一時障害は同じ Capture の retry 回数を増やし、上限で `failed`
- `processing` と `completed` の本文更新は `409`
- `pending` と `failed` の本文更新は Week 3 と同じく許可
- `POST /api/v1/captures/{captureId}/retry` は `failed` だけ。成功したら再び `pending` と新しい outbox 行

`Idempotency-Key` は作成 API の入口に残す。Worker の重複実行防止は別で、`capture_id` と処理世代で判定する。

## 依存の流れ

```text
Browser
  → createCapture（Idempotency-Key）
    → FastAPI
      → Capture 行 + outbox 行（同一 transaction）
      → 202 { data: CaptureResponse, status: pending }
  → 詳細または一覧
    → 短い間隔で getCapture
      → pending / processing の間だけ繰り返す
      → completed / failed で止める

Outbox relay（arq cron）
  → 未配送の outbox を arq job へ
    → Worker
      → processing
      → 状態だけ進める（AI は呼ばない）
      → completed、または retry / failed
```

Web から業務テーブルと queue を直接触らない。Worker は HTTP レスポンスを作らない。失敗の記録は [04](./04-error-handling.md) の Worker 境界で行う。

## ファイル

| ファイル | 要点 |
| --- | --- |
| `supabase/migrations/<timestamp>_capture_outbox.sql` | outbox 表。Capture の status 値は既存 enum を使う |
| `apps/api/src/hibi/jobs/` | arq の入口、relay、Capture の job。業務判断は Capture service へ委譲 |
| `apps/api/src/hibi/modules/captures/service.py` | 作成と outbox を同じ session で書く。状態遷移と retry 上限 |
| `apps/api/src/hibi/modules/captures/router.py` | 作成を `202` にする。`retry` を足す |
| `packages/api-client` | OpenAPI から再生成。`201` 前提のテストを `202` へ更新 |
| `apps/web/src/features/capture/` | `pending` / `processing` の間だけ polling。糸の節に短い文言 |

outbox の配送済み印は、job 投入の成功後に付ける。投入前に消すと、Worker へ届かなかった行が残らない。

## 画面

[21](./21-capture-visual.md) の糸を崩さない。

- `pending` / `processing`: 節を静かに動かし、「整えています」と時刻の近くに出す
- `completed`: 文言を消す。Week 5 まで分類結果は出さない
- `failed`: 「やり直せます」と retry。失敗を赤バッジにしない
- polling は詳細を開いている間と、一覧に未完了がある間だけ。完了後は止める
- `status` の英語値をそのまま画面に出さない

## 実装順

1. outbox の migration と、同一 transaction で Capture と outbox を書くテスト
2. 作成 API を `202` に変え、OpenAPI と client を再生成する
3. relay と arq Worker。二度実行しても `completed` は 1 回
4. 一時障害の retry と、上限後の `failed`
5. `failed` だけの retry endpoint
6. `processing` / `completed` の本文更新を `409` にする
7. Web の polling。未完了のときだけ getCapture を繰り返す
8. API test / worker test / Web test / typecheck / lint を GREEN

## 関連

- [アーキテクチャ方針](./01-architecture.md)
- [プロジェクト構成](./02-project-structure.md)
- [エラーハンドリング](./04-error-handling.md)
- [API・データ契約](./06-api-data-contracts.md)
- [実装スケジュール](./11-implementation-schedule.md)
- [Capture 契約](./13-week3-capture-contract.md)
- [Capture 画面の見た目](./21-capture-visual.md)
