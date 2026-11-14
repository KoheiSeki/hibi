# Week 10: 朝ダイジェスト・週次レビュー

[実装スケジュール](./11-implementation-schedule.md) の Week 10。[Week 9 の Today](./27-week9-today-priority.md) の条件を変えずに、毎朝のダイジェストと、週次レビューを、定期処理で作る。Capture の処理、検索、Today の契約、job 引数は [22-week4-async-capture.md](./22-week4-async-capture.md) から [27-week9-today-priority.md](./27-week9-today-priority.md) のまま壊さない。

## このステップのゴール

ユーザーの timezone の朝 7 時を過ぎたら、その日のダイジェストを 1 件だけ作る。月曜の朝には、先週の週次レビューを 1 件だけ作る。cron を何度回しても、同じ期間の行は増えない。処理に失敗した行は、画面から安全に再実行できる。

完了条件:

- cron を複数回、同時に実行しても、同じユーザー・種類・期間の行は 1 件のまま
- 日付と時刻の境界を、ユーザーの timezone で決める。夏時間の日でも、朝 7 時に作る
- ダイジェストと週次レビューを、API と画面で読める
- 失敗した行を、所有者だけが再実行でき、二重に作られない
- `processing` のまま止まった Capture を、世代を進めて安全に回復できる
- 通常の pytest は LLM を呼ばない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 通知(Web Push、メール) | 余力がある場合だけ。この週は画面で読むところまで |
| 配信時刻の設定 UI | 朝 7 時に固定。設定 UI は timezone の設定と一緒に後続 |
| 過去の日付の backfill | 作るのは、現在の期間だけ。止まっていた間の日は作らない |
| 週次レビューの回答生成や対話 | 要約を 1 回作るだけ |
| 検索条件、Today の優先度の変更 | Week 8、Week 9 のまま。ダイジェストは Today の結果を読む |
| provider の自動切り替え | 障害は retry し、別 provider へは切り替えない |
| ダイジェストの編集、削除 | 読み取り専用 |

## 用語

| 語 | 意味 |
| --- | --- |
| ダイジェスト | その日の朝に、今日やることを 1 件にまとめたもの。`kind = daily` |
| 週次レビュー | 先週の記録と完了を、LLM の要約つきでまとめたもの。`kind = weekly` |
| 期間の日付 | ユーザーの timezone での暦日。ダイジェストはその日、週次レビューは週の月曜 |

## 作る時刻

cron は 15 分ごとに `run_daily_digest` を回す。ユーザーごとの予定は持たない。実行のたびに、次の条件を満たすユーザーを探して、足りない行だけを作る。

| 種類 | 条件 |
| --- | --- |
| daily | ユーザーの現地時刻が 7 時以降で、その日の daily の行が無い |
| weekly | 月曜で、現地時刻が 7 時以降で、先週の weekly の行が無い |

対象にするのは、直近 14 日以内に Capture があるユーザーだけにする。休眠中のユーザーに、空の行を作り続けない。

- **夏時間:** 暦日の加算で決める。24 時間を足さない。現地の 7 時が存在する日は、必ず 7 時以降に作る。判定は [Week 9 の](./27-week9-today-priority.md) `local_day_end` と同じく、純粋関数にして、現在時刻と timezone を引数で渡す。
- **止まっていた場合:** 7 時を過ぎていれば、その日のうちは作る。翌日になったら、前の日の分は作らない。
- **同時実行:** 複数の worker や cron が重なっても、行は 1 件になる(次の「契約」)。

## 契約

`app.digest_reports` を追加する。

| 列 | 内容 |
| --- | --- |
| `id` | PK。アプリが `uuid.uuid7()` で発行 |
| `user_id` | 所有者。`app.profiles(user_id)` への FK |
| `kind` | `daily` または `weekly` |
| `period_start` | `date`。ユーザーの暦日。daily はその日、weekly は週の月曜 |
| `timezone` | 作ったときに使った IANA 名 |
| `status` | `pending`、`ready`、`failed` |
| `content` | `jsonb`。`ready` のときだけ。中身は下の「内容」 |
| `content_version` | `daily-digest-v1`、`weekly-review-v1` |
| `summary_model` | 週次レビューの要約に使ったモデル名。daily と、fake は null か fake の名前 |
| `error_code` | `failed` のときの理由。LLM の timeout など。個人情報を含めない |
| `generated_at` | `ready` になった時刻 |
| `created_at`、`updated_at` | `timestamptz` |

`(user_id, kind, period_start)` に unique を付ける。権限は `app.captures` と同じで、`anon` と `authenticated` から剥奪し、`hibi_runtime` に CRUD を渡す。

### 冪等な作り方

行の作成は、`INSERT ... ON CONFLICT DO NOTHING` で、`pending` の行を先に入れる。入れた処理だけが、中身を作って `ready` にする。入れられなかった処理は、何もせず終わる。同時に 2 つが走っても、中身を作るのは 1 つだけになる。

arq への投入には `_job_id = digest:{kind}:{user_id}:{period_start}` を付け、同じ期間の重複投入も避ける。ただし正本は DB の unique で、job id は補助にとどめる。

### 内容

daily(`daily-digest-v1`)は LLM を使わず、決定論的に作る。

```text
items               Today の上位 5 件。captureId、title、dueAt
overdueCount        期限が過ぎた未完了の件数
dueTodayCount       今日が期限の未完了の件数
doneYesterdayCount  昨日、完了にした件数
```

`items` は、そのユーザーの timezone と現在時刻で、Week 9 の `rank_today` を呼んで求める。優先度の計算は変えない。

weekly(`weekly-review-v1`)は、決定論的な集計に、LLM の要約を足す。

```text
stats    capturedCount、doneCount、openCount、overdueCount
summary  500 文字以内の要約
```

- LLM に渡すのは、集計と、完了にしたシナリオの title だけ。本文(`raw_text`)は送らない。
- 先週に Capture が 1 件も無ければ、LLM を呼ばず、定型の要約にする。
- structured output は `{"summary": "..."}` だけにする。不正なときは再試行せず、定型文で `ready` にする([Week 6](./24-week6-llm-system-two.md) と同じ)。
- timeout、接続失敗、429、5xx は例外にして、job の retry に乗せる。3 回目で `failed` にする。

### API

`GET /api/v1/digest-reports`。`kind` は任意で、`limit` は 1 以上 30 以下で未指定は 7。`fromDate` は任意で、`period_start` の下限。新しい順に返す。成功は 200 で、0 件は空配列。範囲外は 422。

`POST /api/v1/digest-reports/{id}/retry`。`failed` の行だけを `pending` に戻し、再実行を予約する。成功は 202。`failed` 以外は 409。所有者でない、または無ければ 404。

OpenAPI と client は、同じ変更で再生成する。

## 再実行と回復

[Week 4 の outbox](./22-week4-async-capture.md) の仕組みを、ダイジェストにも使う。

| 項目 | 扱い |
| --- | --- |
| outbox | `aggregate_type` に `digest_report` を足す(check を広げる)。retry の API は、状態の更新と outbox の追加を同じ transaction で行う |
| job | `generate_digest_report_job(report_id)`。引数は id だけ。`max_tries = 3`。3 回目で `failed` |
| `pending` のまま止まった行 | 10 分を過ぎたら、cron が再投入する。job は `pending` のときだけ中身を作るので、二重に作らない |
| `processing` のまま止まった Capture | 10 分を過ぎたら、cron が処理の世代を 1 進めて、`pending` に戻し、outbox を足す。古い世代の job は、世代が合わず、何も変えない |

「止まった Capture」の回復は、利用者の retry(`failed` の Capture)と同じ仕組みを、システムが自動で使うもの。新しい状態は増やさない。

## 画面

`/captures/digest` を足す。Capture 画面と同じ layout、色のトークン、糸と節を使う。ヘッダーに「ダイジェスト」のリンクを足す。

- 最新の daily を先に出す。今日やることの上位、期限超過と今日が期限の件数、昨日の完了数
- その下に、最新の weekly を出す。集計と要約
- 行は、押すと詳細へ行く
- 何も無いときは、糸の最初の節として、「ダイジェストは毎朝 7 時に作ります」を出す
- `failed` の行には、理由の一言と「もう一度作る」を出す。成功すると `pending` の表示にする
- `pending` は「作っています」を出す。更新の仕組みは、Week 4 の polling を使う
- バッジと緊急度の色分けは足さない

## 障害

| 結果 | 扱い |
| --- | --- |
| LLM の timeout、接続失敗、429、5xx | 例外にして job の retry に乗せる。3 回目で `failed` |
| structured output が不正 | 定型文で `ready`。再試行しない |
| ユーザーのプロフィールが無い、timezone 名が不正 | `UTC` として扱い、例外にしない |
| 同じ期間の行が既にある | 何もせず終える。例外にしない |
| `retry` が `failed` 以外 | 409 |
| 別ユーザーの行 | 404 |

## ログとメトリクス

構造化ログに、`digest_generated`、`digest_failed`、`stuck_capture_recovered` を出す。項目は kind、期間、所要時間、結果。ユーザーの内容と本文は出さない。daily の成功率は、このログから集計できるようにする([運用](./09-operations.md))。

## テスト

- 作る時刻の判定は、純粋関数でテストする。現在時刻と timezone を渡す。`America/New_York` の 23 時間の日と 25 時間の日で、7 時以降だけが対象になる
- 月曜の判定。先週の週の月曜が、ユーザーの暦日で決まる
- cron を 2 回続けて、同時に 2 つ実行しても、行が 1 件のまま(`integration`)
- daily の `items` が、Week 9 の `rank_today` と同じ並びになる
- weekly で、LLM の呼び出し回数が 1 回で、通常の pytest では fake が使われる。Capture が無い週は、呼び出しが 0 回
- LLM の timeout は 3 回目で `failed`。不正な出力は定型文で `ready`
- retry が `failed` だけを `pending` に戻し、outbox が 1 件増える。`failed` 以外は 409、他人の行は 404
- `processing` のまま止まった Capture が、世代が進んで `pending` に戻り、古い世代の job が何も変えない
- 所有者分離と unique の検証は `integration` にし、通常 pytest から除外する
- 画面の手動確認は、朝 7 時を過ぎたあとに、daily が 1 件だけ出ること。weekly が月曜に出ること。`failed` の行を「もう一度作る」で戻せること

## **実装順**

1. 作る時刻の判定と、daily の内容の組み立てを、純粋関数のテストで GREEN にする。DB も network も使わない
2. migration(`digest_reports`、outbox の check)と、冪等な作成(`ON CONFLICT DO NOTHING` の claim)を書く
3. `run_daily_digest` の cron と、`generate_digest_report_job` を足す。daily だけを先に通す
4. weekly の集計と、LLM の要約(port、fake、実 adapter)を足す
5. 一覧 API と、retry API を所有者条件つきで追加し、OpenAPI client を再生成する
6. 止まった Capture と `pending` の回復を、cron に足す
7. `/captures/digest` の画面を足す
8. API test / worker test / typecheck / lint を GREEN にする

通知を足すなら、ダイジェストの `ready` を契機にする。Week 11 では、ここで足した構造化ログとメトリクスを、運用の監視に載せる。
