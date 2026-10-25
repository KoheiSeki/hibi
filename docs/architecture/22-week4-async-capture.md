# Week 4: Capture の非同期処理

[実装スケジュール](./11-implementation-schedule.md) の Week 4。[Capture 処理](./01-architecture.md#capture処理) の 2〜4 と 9 を、AI なしで通す。Jev / LLM は Week 5 以降。見た目は [Capture 画面の見た目](./21-capture-visual.md)。Week 3 の作成・冪等・所有者は [13-week3-capture-contract.md](./13-week3-capture-contract.md) のまま壊さない。

## このステップのゴール

Capture の保存と「処理を始める」記録を、同じ transaction で残す。API は待たずに `202 Accepted` を返す。別プロセスの Worker が状態を `pending` から `completed` または `failed` へ進める。画面は未完了のあいだだけ単体取得を繰り返し、糸の上で処理中だと分かる。

完了条件:

- 新規作成は `202 Accepted`。body は `ApiResponse[CaptureResponse]`。`Location` は残す
- 同じ `Idempotency-Key` と同じ本文の再送は、新規行を作らず現在の Capture を `200` で返す
- Worker 完了まで `GET /api/v1/captures/{captureId}` の `status` で追える
- 同じ job を二度実行しても `completed` は 1 回で、本文は増えない
- 一時障害は最大 3 回まで retry し、そのあと `failed`
- 検証エラーと、所有者不一致は retry しない
- `processing` と `completed` の本文更新は `409`

## やらないこと

| 先送り | 理由 |
| --- | --- |
| Jev / LLM / Embedding / 分類結果の保存 | Week 5 以降。Worker は状態遷移だけ |
| SSE / Supabase Realtime | polling の負荷か UX の問題を測ってから |
| カテゴリ、緊急度、route の表示 | 判定結果がまだない |
| status バッジ、色分け、番号 | [21](./21-capture-visual.md) |
| Render Cron と arq cron の併用 | cron は arq に一本化する |
| Alembic | migration は `supabase/migrations` だけ |
| Web から queue や `app` schema を直接読む | [01](./01-architecture.md) |

## 状態

`app.captures.status` は Week 3 の check のまま使う。値の追加 migration は不要。

```text
pending → processing → completed
                    └→ failed → pending
```

| 遷移 | 誰が書く | 条件 |
| --- | --- | --- |
| 作成で `pending` | Capture service | outbox 1 行と同じ transaction |
| `pending` → `processing` | Worker 開始 | 対象が `pending` のときだけ |
| `processing` → `completed` | Worker 正常終了 | 対象が、その job の処理世代と一致する `processing` |
| `processing` → `failed` | Worker | 一時障害が 3 回に達したとき |
| `failed` → `pending` | retry endpoint | 所有者が `failed` の Capture を再実行したとき。新しい outbox 1 行 |

すでに `completed` の job は何も書き換えない。`failed` や別世代の job も、古い世代なら何も書き換えない。

本文更新:

- `pending` と `failed` は Week 3 と同じく許可
- `processing` と `completed` は `409`
- 削除は状態に関係なく、所有者なら Week 3 と同じく許可。削除したら未配送の outbox は配送しない

## 冪等の二層

作成 API の `Idempotency-Key` は残す。スコープ、hash、409 は Week 3 のまま。

| 状況 | HTTP | 中身 |
| --- | --- | --- |
| 初回作成 | `202` | 新しい Capture。`status` は `pending` |
| 同じ key・同じ本文 | `200` | 既存行を返す。outbox は足さない。`status` は今の値 |
| 同じ key・別本文 | `409` | Week 3 の `idempotency-key-conflict` |

Worker の重複防止は別である。job の引数は `capture_id` と `processing_generation` だけにする。`processing_generation` は Capture 行の整数で、作成時は `1`、利用者が retry するたびに `1` 増やす。Worker は「今の世代」と引数が一致するときだけ遷移する。

## Outbox

表は `app.outbox_events`。Data API には出さない。`public` / `anon` / `authenticated` から権限を外し、`hibi_runtime` にだけ DML を渡す。Capture 本体と同じ。

| 列 | 意味 |
| --- | --- |
| `id` | uuid。主キー |
| `user_id` | 所有者。relay の認可には使わず、追跡用 |
| `aggregate_type` | この週は `capture` 固定 |
| `aggregate_id` | `captures.id` |
| `event_type` | この週は `capture.processing_requested` 固定 |
| `processing_generation` | job に渡す世代 |
| `status` | `pending` または `published` |
| `available_at` | この時刻以降に配送してよい |
| `published_at` | job 投入に成功した時刻。未配送は null |
| `created_at` | 作成時刻 |

配送済みにするのは、arq への投入が成功したあとだけ。投入前に `published` にすると、Worker へ届かなかった行が残らない。

Capture 行を削除したら、その `aggregate_id` の `pending` 行は配送対象から外す。

## Transaction と relay

作成の 1 回の session で、次を両方書く。途中で例外なら session dependency が rollback する。outbox だけ、または Capture だけが残る状態を作らない。

```text
captures へ insert（status = pending, processing_generation = 1）
outbox_events へ insert（status = pending, 同じ generation）
commit
202 を返す
```

relay は arq cron で `relay_outbox_events` を短い間隔（5 秒）で回す。1 回で取る件数は 20 まで。各行について `process_capture_job` を enqueue し、成功したらその行だけ `published` と `published_at` を書く。enqueue に失敗した行は `pending` のまま、次の cron で拾う。

Worker は HTTP を返さない。一時障害は例外を arq の retry に乗せる。検証エラーと「所有者の行ではない」は例外にせず、その job を終了する。Capture がすでに無い job も終了する。構造化ログと失敗の記録は [04](./04-error-handling.md) の Worker 境界。

一時障害の上限は 3。回数は outbox ではなく、その世代の Worker 試行として Capture service が数える。3 回目の失敗で `failed`。4 回目以降の job は状態を変えない。

## HTTP

| 操作 | Week 3 | Week 4 |
| --- | --- | --- |
| `POST /api/v1/captures` 初回 | `201` | `202`。body と `Location` は維持 |
| 同じ key の再送 | `200` | `200` のまま。outbox は足さない |
| `GET` 単体・一覧 | `200` | 変えない。`status` が遷移する |
| `PATCH` | `200` | `processing` / `completed` は `409` |
| `DELETE` | `204` | 変えない |
| `POST /api/v1/captures/{captureId}/retry` | なし | `failed` だけ `202`。それ以外の状態は `409`。他者・不存在は `404` |

`retry` は resource の CRUD で表せない command なので、path の末尾に動詞を置く。[03](./03-naming-conventions.md) の command の例外。

OpenAPI と `packages/api-client` は同じ変更で再生成する。Web の作成成功判定は、生成 client が `202` を成功とすることに合わせる。`201` だけを成功とみなすテストは、この週の意図した変更として更新する。

## 画面

[21](./21-capture-visual.md) の糸を崩さない。英語の `status` は出さない。

| status | 一覧と詳細 | polling |
| --- | --- | --- |
| `pending` / `processing` | 節を静かに動かし、時刻の近くに「整えています」 | 3 秒ごとに `getCapture`。画面を離れたら止める |
| `completed` | 文言を消す。分類結果は出さない | 止める |
| `failed` | 「やり直せます」と retry。赤バッジにしない | 止める |

polling は詳細を開いているあいだと、一覧に未完了が 1 件でもあるあいだだけ。完了した行のために一覧全体を置き換えない。取得失敗は Week 3 のエラー表示を使い、polling を止めて再試行できるようにする。

作成直後の Capture は `pending` なので、成功メッセージのあと詳細へ遷移しなくても、一覧のその行が「整えています」になる。

## ファイル

| ファイル | 要点 |
| --- | --- |
| `supabase/migrations/<timestamp>_capture_outbox.sql` | `app.outbox_events` と `captures.processing_generation` |
| `apps/api/src/hibi/jobs/main.py` | arq の入口と cron |
| `apps/api/src/hibi/jobs/relay_outbox_events.py` | 未配送を enqueue し、成功後に `published` |
| `apps/api/src/hibi/jobs/process_capture_job.py` | 引数を検証し、Capture service を呼ぶだけ |
| `apps/api/src/hibi/modules/captures/service.py` | 同一 transaction、遷移、retry 上限、409 |
| `apps/api/src/hibi/modules/captures/repository.py` | outbox の追加と配送済み更新。query には `user_id` |
| `apps/api/src/hibi/modules/captures/router.py` | `202` と `retry` |
| `packages/api-client` | 再生成 |
| `apps/web/src/features/capture/` | 未完了のあいだだけの polling と文言 |

`jobs/` に業務ルールを書かない。状態を変えてよいかは service が決める。

## テスト

API / DB:

- 作成が成功すると Capture と outbox が両方ある。片方が失敗すると両方ない
- 初回は `202`、同じ key の再送は `200` で outbox が増えない
- Worker が `pending` を `processing` にしてから `completed` にする
- 同じ generation の job を二度実行しても、2 回目は no-op
- 古い generation の job は、retry 後の新しい状態を上書きしない
- 一時障害 3 回で `failed`。4 回目は状態を変えない
- `processing` の `PATCH` は `409`。`failed` の retry は `202`。`completed` の retry は `409`
- 他者の retry は `404`

Web:

- `pending` の詳細は「整えています」を出し、完了後に消す
- `failed` は「やり直せます」を出す
- `completed` では追加の getCapture を呼ばない
- 一覧の未完了行だけが polling の対象になる

OpenAPI の `operationId` と `202` は contract で固定する。Week 3 の `201` 期待は、この週の変更として明示的に置き換える。

## 実装順

1. migration と repository。同一 transaction の失敗で両方残らないことを先にテストする
2. service の作成を outbox 付きに変える。HTTP はまだ `201` のままでも、DB のテストを先に GREEN にする
3. router を `202` にし、client を再生成する。Web の作成成功を `202` で通す
4. `process_capture_job` を service 経由で単体テストする。arq の起動は、この次でよい
5. relay と cron。enqueue 成功後だけ `published`
6. retry 上限と `failed`
7. `POST .../retry` と、処理中・完了後の `409`
8. Web の polling と文言。見た目の微調整は、状態遷移が見えてから
9. API test / worker test / Web test / typecheck / lint を GREEN

Week 5 では、`completed` の直前に Jev の結果保存を挟む。この週の job 引数と世代判定は変えない。
