# Week 7: 3つの日常シナリオ

[実装スケジュール](./11-implementation-schedule.md) の Week 7。[Capture 処理](./01-architecture.md#capture処理) の 6 のうち、確定した `shopping`、`reminder`、`expense` の実行までを通す。聞き返しの生成条件、category、confidence、route、policy version、job 引数は [24-week6-llm-system-two.md](./24-week6-llm-system-two.md) のまま壊さない。

## このステップのゴール

高 confidence で route が `shopping`、`reminder`、`expense` のときだけ、決定論的な抽出結果を `proposed` として保存する。ユーザーが詳細画面で確認したときだけ `accepted` にする。`clarify`、`note`、`chat` はシナリオを作らない。Worker は確認を代行しない。

完了条件:

- `牛乳を買う` は買い物として `proposed` になる
- `明日の 9 時に起こして` は予定として `proposed` になる
- `ランチ 1200 円` は支出として `proposed` になり、金額は 1200 になる
- `境界未満の牛乳` は `clarify` のままシナリオを作らず、聞き返し文を詳細に出す
- `あとで読む記事` と `今日どうだった` は `completed` のままシナリオを作らない
- 確認は所有者だけができ、別ユーザーは 404 になる
- 未確認のまま外部送信、削除、支払い、予定の登録は行わない
- 通常の pytest は Jev も LLM も呼ばない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 外部カレンダー、買い物先、決済 | この週の結果はアプリ内の提案だけ |
| 聞き返しへの返答で再分類する | 表示まで。対話は後続 |
| Embedding / RAG | Week 8 |
| Today の優先度、期限の timezone 計算 | Week 9。予定の文言はこの週は文字列のまま |
| 朝ダイジェスト、通知 | Week 10 |
| Playwright の常設 E2E | Week 12。この週は認証済み API と画面の手動確認 |
| job 引数の追加 | `capture_id` と `processing_generation` のまま |
| 一覧のバッジと色分け | [Capture 画面の見た目](./21-capture-visual.md) を壊さない |

## 挿入位置

`process_capture` で route が決まったあと、聞き返しの有無に続けてシナリオを決める。分類列、聞き返し文、シナリオは同じ generation の完了更新で書く。

```text
分類して route を決める
clarify なら聞き返し文を 1 回作る
shopping、reminder、expense なら提案を作る
それ以外は提案を作らない
同じ generation の completed として保存する
```

確認は job の外に置く。詳細の「追加する」が、所有者の `proposed` を `accepted` にする。

## 契約

`app.capture_scenarios` を追加する。`capture_id` が主キーで、`app.captures` を参照する。1 Capture につき 1 行まで。

| 列 | 内容 |
| --- | --- |
| `capture_id` | Capture の id |
| `user_id` | 所有者。Capture と同じ値 |
| `route` | `shopping`、`reminder`、`expense` のいずれか |
| `status` | `proposed` または `accepted` |
| `title` | 1 文字以上 200 文字以下 |
| `amount` | 円の整数。支出以外と、金額が取れない支出は null |
| `remind_text` | 予定の時刻表現。予定以外は null。1 文字以上 200 文字以下 |
| `policy_version` | `capture-scenario-v1` |
| `created_at`、`updated_at` | timestamptz |

分類の 7 列チェックには入れない。Capture が `completed` でないシナリオは作らない。

`CaptureResponse.scenario` は optional。未設定は null。中身は `route`、`status`、`title`、`amount`、`remindText`、`policyVersion`。OpenAPI と client は同じ変更で再生成する。

確認は `POST /api/v1/captures/{capture_id}/scenario/accept`。成功は 200 で、`status` が `accepted` の Capture を返す。所有者でない、またはシナリオが無い場合は 404。`accepted` 済みと、`proposed` 以外は 409。

## Policy

定数は `CAPTURE_SCENARIO_POLICY_VERSION = "capture-scenario-v1"`。実行する route は `shopping`、`reminder`、`expense` だけ。

| route | 保存 |
| --- | --- |
| `shopping`、`reminder`、`expense` | `proposed` を 1 行作る |
| `clarify`、`note`、`chat` | 行を作らない |

抽出は LLM に任せない。評価 dataset の 3 文は次で固定する。

| 本文 | title | amount | remind_text |
| --- | --- | --- | --- |
| `牛乳を買う`、`境界の牛乳` | `牛乳` | null | null |
| `明日の 9 時に起こして` | `起こして` | null | `明日の 9 時` |
| `ランチ 1200 円` | `ランチ` | 1200 | null |

dataset に無い高 confidence の本文は、title を trim した本文にし、amount と remind_text は null にする。支出で `円` の直前に整数があるときだけ、その整数を amount にする。

Worker が書いてよい status は `proposed` だけ。`accepted` へ進めるのは確認 API だけ。

## 画面

一覧の糸と節は変えない。シナリオと聞き返しは詳細だけに出す。

- `completed` かつシナリオがあるとき、title を本文の下に出す。支出で amount があるときは `1,200円` を併記する。予定で `remind_text` があるときはその文字列を併記する
- `proposed` のときだけ「追加する」を出す。成功後は `accepted` になり、ボタンを隠して「追加しました」を出す
- `clarificationText` があるときは、その文字列を詳細に出す。シナリオのボタンは出さない
- `pending`、`processing`、`failed`、空一覧、取得エラーは Week 4 の文言と polling のまま

色のトークンは [Capture 画面の見た目](./21-capture-visual.md) に合わせる。バッジと処理状態の色分けは足さない。

## テスト

- dataset の 3 文は、上記の title、amount、remind_text で `proposed` になる
- `clarify`、`note`、`chat` はシナリオが null
- 高 confidence のシナリオ作成で `llm_call_count()` は増えない
- job は `accepted` を書かない
- 所有者の accept は 200 で `accepted` になる
- 別ユーザーと、シナリオの無い Capture は 404
- 再実行の accept は 409
- 所有者分離の DB 検証は `integration` にし、通常 pytest から除外する
- 画面の手動確認は、3 文が詳細に出て、「追加する」で「追加しました」に変わること。別アカウントからその詳細が 404 になること

## 実装順

1. route ごとの実行可否と、3 文の抽出をテストで GREEN にする。DB も LLM も使わない
2. migration と、完了更新と同じ条件で `proposed` を書く
3. `process_capture` から policy と抽出を呼ぶ。`clarify`、`note`、`chat` では書かない
4. accept API を所有者と `proposed` に限定する
5. response の optional `scenario` と OpenAPI client を再生成する
6. 詳細へ聞き返し文、提案、確認ボタンを足す。一覧は変えない
7. API test / worker test / typecheck / lint を GREEN にする

Week 8 では、確定した note を含む過去の記録を検索する。シナリオの確認条件は変えない。
