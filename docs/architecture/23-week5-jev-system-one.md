# Week 5: Jev System One

[実装スケジュール](./11-implementation-schedule.md) の Week 5。[Capture 処理](./01-architecture.md#capture処理) の 5 と 6 と 8 のうち、分類と決定論的 route までを通す。LLM の聞き返し文は Week 6。見た目の分類表示は Week 7 のシナリオまで出さない。Week 4 の job 引数、世代判定、202、polling は [22-week4-async-capture.md](./22-week4-async-capture.md) のまま壊さない。

## このステップのゴール

Worker が `processing` のあいだに Jev へ分類を依頼し、決定論的 policy が route を決めてから `completed` にする。結果、confidence、policy version、質問 version を Capture に残す。通常の CI は Jev を呼ばず、fake と評価 dataset だけで再現する。

完了条件:

- `shopping`、`reminder`、`expense`、`note`、`chat` を分類できる
- confidence 閾値の境界をテストできる
- mock（fake port）だけで CI が課金なしで通る
- 同じ dataset と policy version で評価結果を再現できる
- Jev の timeout など一時障害は Week 4 の retry に乗り、3 回で `failed` になる
- 低 confidence でも LLM は呼ばない。route は `clarify` として保存し、status は `completed`

## やらないこと

| 先送り | 理由 |
| --- | --- |
| LLM、聞き返し文、structured output | Week 6 |
| カテゴリ、緊急度、route の画面表示 | 判定の保存が先。表示は Week 7 のシナリオ |
| Embedding / pgvector | Week 8 |
| Today の優先度計算 | Week 9。urgency の保存だけこの週 |
| 本番 Jev の必須化 | キーが無い環境では fake。実呼び出しは明示した評価実行だけ |
| job 引数への分類結果の追加 | 世代判定は `capture_id` と `processing_generation` のまま |
| status バッジ、色分け | [21](./21-capture-visual.md) |

## 挿入位置

`CaptureService.process_capture` の `processing` 更新が成功したあと、`completed` の直前に分類を入れる。Week 4 の TODO（分類、文章生成）のうち、文章生成はまだ書かない。

```text
pending のときだけ processing にする
分類 port を呼ぶ
policy が route を決める
同じ generation の processing のときだけ結果を保存して completed にする
```

世代が一致しない、すでに `completed` / `failed`、途中で行が無い場合は Week 4 と同じく no-op。分類結果を古い世代で上書きしない。

Jev が一時障害（timeout、接続失敗、5xx）を返したら例外のまま Job 境界へ返す。Week 4 の 3 回上限と、最終失敗時の別 transaction の `failed` を再利用する。入力が空、質問 version 不一致、分類結果の schema 不正は一時障害ではない。retry せず、その job を終了して `failed` にはしない。ログを残し、Capture は `processing` のままにしない。検証不能な結果は `failed` にせず、route を `clarify`、confidence を `0` として `completed` にする。利用者が retry する対象は、外部障害で残った `failed` だけにする。

## 契約

分類結果は Capture の追加列にする。別テーブルは作らない。response へ出す場合は optional とし、既存 client を壊さない。英語の status は画面に出さない。

| 列 | 意味 |
| --- | --- |
| `category` | `shopping` / `reminder` / `expense` / `note` / `chat`。未処理は null |
| `route` | policy の結果。高 confidence は category と同じ。未満は `clarify` |
| `urgency` | `low` / `normal` / `high`。policy が score から決める |
| `confidence` | `0` 以上 `1` 以下の数値 |
| `policy_version` | この週は `capture-route-v1` 固定 |
| `question_version` | `docs/ai/jev-questions.md` の version と一致 |
| `processed_at` | `completed` にした時刻。未完了は null |

閾値は policy 内の定数 `0.70`。`0.70` 以上は category を route にする。`0.70` 未満は route を `clarify` にする。urgency は score を受け取っても、この週の policy は `normal` 固定でよい。境界のテストが先で、補正ルールは Week 9。

質問文、許可する category、version は `docs/ai/jev-questions.md` に書く。コードの version 定数と文書の version がズレたらテストで落とす。

HTTP:

- 作成、取得、一覧、更新、削除、retry の status code は Week 4 のまま
- `CaptureResponse` に上の列を optional で足す。未処理は field を欠くか null
- OpenAPI と `packages/api-client` は同じ変更で再生成する
- Web の polling は status だけを見る。category は表示しない

## Port

SDK 型を service へ漏らさない。port は `apps/api/src/hibi/ai/` に置く。

```text
classify_capture(text, *, question_version) -> Classification
```

`Classification` は category、confidence、urgency score、question version だけを持つ dataclass。route は port の外、`policies.py` の `decide_capture_route` が決める。

| 実装 | 用途 |
| --- | --- |
| `FakeCaptureClassifier` | CI と単体テスト。dataset のキーワードで 5 分類を返す。network しない |
| `JevCaptureClassifier` | 実 Jev。timeout を持つ。未設定なら起動時に作らない |

service は port だけに依存する。`process_capture_job` は service を呼ぶだけで、Jev SDK を import しない。

## 評価

`docs/ai/evals/capture-route-v1.jsonl` に代表入力を version 管理する。1 行は `rawText`、`category`、`confidence`、期待 `route`。`category` と `confidence` は fake の戻り値、`route` は policy の期待値。本番の利用者入力はコピーしない。正本は [jev-questions.md](../ai/jev-questions.md) とこの jsonl。

評価コマンドは fake classifier と `decide_capture_route` だけを通す。pytest の通常実行に含め、Jev の API キーが無くても GREEN になる。実 Jev との突合は、キーがあるときだけの手動または別 marker とし、CI の必須にしない。

最低限の行:

- 牛乳を買う → `shopping` / `shopping`
- 明日の 9 時に起こして → `reminder` / `reminder`
- ランチ 1200 円 → `expense` / `expense`
- あとで読む記事 → `note` / `note`
- 今日どうだった → `chat` / `chat`
- confidence が `0.70` ちょうどの境界
- confidence が `0.69` のとき route は `clarify`、category は保持

## ファイル

| ファイル | 要点 |
| --- | --- |
| `docs/ai/jev-questions.md` | 質問文、許可 category、`question_version` |
| `docs/ai/evals/capture-route-v1.jsonl` | 再現用 dataset |
| `supabase/migrations/<timestamp>_capture_classification.sql` | 上記列と check。Alembic は使わない |
| `apps/api/src/hibi/ai/classification.py` | port と結果 dataclass |
| `apps/api/src/hibi/ai/fake_classifier.py` | dataset と同じ規則の fake |
| `apps/api/src/hibi/ai/jev_classifier.py` | timeout 付きの実 adapter。CI では使わない |
| `apps/api/src/hibi/modules/captures/policies.py` | `decide_capture_route`。副作用なし |
| `apps/api/src/hibi/modules/captures/service.py` | `completed` の直前で分類と保存 |
| `apps/api/src/hibi/modules/captures/repository.py` | 同じ generation のときだけ分類列を書く |
| `packages/api-client` | optional field を再生成 |

## テスト

- fake が 5 category を返す
- policy が `0.70` 以上で category を route にし、未満で `clarify` にする
- `process_capture` が分類列と `processed_at` を残して `completed` にする
- 同じ generation の再実行は分類列を増やさず、本文も変えない
- 古い generation は新しい分類を上書きしない
- timeout は例外になり、3 回目で `failed`。4 回目は状態を変えない
- schema 不正の結果は retry せず、`clarify` / confidence `0` で `completed`
- dataset の全行が fake + policy で期待 route と一致する
- `question_version` 定数と `docs/ai/jev-questions.md` が一致する
- OpenAPI の既存 operation と 202 / 409 が変わらない

## 実装順

1. `docs/ai/jev-questions.md` と評価 dataset を先に固定する
2. policy を dataset の境界テストで GREEN にする。Jev も DB もまだ呼ばない
3. fake classifier を dataset の 5 分類で GREEN にする
4. migration と、分類列を条件付きで書く repository
5. `process_capture` の `completed` 直前へ fake を差し込む。job 引数は変えない
6. timeout を一時障害、schema 不正を非 retry としてテストする
7. response の optional field と OpenAPI client を再生成する。Web の表示は変えない
8. 実 Jev adapter は port の外側に置き、通常 pytest から除外する
9. API test / worker test / dataset 評価 / typecheck / lint を GREEN にする

Week 6 では、route が `clarify` のときだけ LLM で聞き返し文を作る。この週の category、confidence、policy version は変えない。
