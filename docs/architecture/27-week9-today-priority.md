# Week 9: Today 優先度

[実装スケジュール](./11-implementation-schedule.md) の Week 9。[Capture 処理](./01-architecture.md#capture処理) で保存した緊急度と期限から、「今日やること」を安定した順序で返す。聞き返し、シナリオの確認、検索、job 引数は [25-week7-daily-scenarios.md](./25-week7-daily-scenarios.md) と [26-week8-search.md](./26-week8-search.md) のまま壊さない。

## このステップのゴール

所有者の完了済みシナリオのうち、未完了で今日までに期限が来るものを、優先度の高い順に最大 N 件返す。「今日」はユーザーの timezone の暦日で決める。同点でも順序は毎回同じになる。対象がなければ空配列を返し、画面は empty state を出す。

完了条件:

- `明日の 9 時に起こして` は、記録した翌日の朝 9 時(ユーザーの timezone)を期限として保存する
- 期限が過ぎた行は、同じ緊急度の期限なしの行より上に出る
- 期限が明日以降の行は出ない
- 日付の境界は、ユーザーの暦日の終わり(翌日の 0 時)で決まる。夏時間の日でも同じ
- 完了にした行は出ない。取り消すと戻る
- 別ユーザーの行、`pending`、`processing`、`failed`、シナリオの無い行は出ない
- 同点の順序が固定されている
- 通常の pytest は Jev、LLM、embedding API を呼ばない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| timezone の設定 UI | 既定を `Asia/Tokyo` にして、設定は後続 |
| 午前・午後以外の時刻表現(`夕方`、`来週` など) | 決定論的に直せる表現だけにする |
| 繰り返しの予定 | Week 10 以降 |
| urgency の label(`low` / `normal` / `high`)の変更 | Week 5 のまま `normal` 固定。優先度は score から直接計算する |
| 朝ダイジェスト、通知 | Week 10 |
| 過去のシナリオの期限の backfill | 既存の行は `due_at` が null のまま。完了にするまで Today に出続ける |
| 優先度の数値を API に出す | 順序だけ返す |

## 挿入位置

`process_capture` で route が決まったあと、分類列と同じ完了更新で `urgency_score` を保存する。route が `reminder` のときだけ、プロフィールの timezone と現在時刻から `due_at` を求め、シナリオと同じ更新で保存する。Today の取得は job の外に置く。

```text
分類して route を決める
urgency_score を保存する
reminder なら remind_text を取り出し、due_at に直す
completed として保存する
```

Today は読み取りのとき、保存済みの `urgency_score` と `due_at` から優先度を計算する。優先度は保存しない。

## 契約

`app.captures` に `urgency_score numeric(3,2)` を足す。null または 0 以上 1 以下。分類の 7 列チェックには入れない。Jev の返す score が範囲外のときは保存しない(null)。

`app.capture_scenarios` に次を足す。

| 列 | 内容 |
| --- | --- |
| `due_at` | timestamptz。`reminder` で時刻表現を直せたときだけ。他は null |
| `done_at` | timestamptz。完了にした時刻。未完了は null |

`app.profiles.timezone` の既定を `Asia/Tokyo` にする。既に `UTC` のままの行も `Asia/Tokyo` に更新する。画面は今も `Asia/Tokyo` 固定のため、日付の境界を画面と合わせる。この書き換えは 2026-11-10 に承認済み。ローカルの開発データだけが対象で、本番の環境ができた後は、行の更新ではなく設定 UI で変える。

`CaptureResponse.scenario` に `dueAt`、`doneAt` を足す(どちらも null 可)。OpenAPI と client は同じ変更で再生成する。

Today は `GET /api/v1/captures/today`。`limit` は 1 以上 20 以下で、未指定は 5。範囲外は 422。成功は 200 で、一覧と同じ要素を優先度の高い順に返す。0 件は空配列。path は `/{capture_id}` より前に登録する。

完了は `POST /api/v1/captures/{capture_id}/scenario/done`、取り消しは `DELETE /api/v1/captures/{capture_id}/scenario/done`。どちらも 200 で Capture を返す。所有者でない、またはシナリオが無い場合は 404。繰り返しても 200 で、`done_at` は最初の時刻のまま残す。

## 期限の求め方

`reminder` の本文から次の表現を取り出し、`remind_text` に入れる。dataset の `明日の 9 時に起こして` は従来どおり `明日の 9 時`。

| 部分 | 規則 |
| --- | --- |
| 日 | `今日`(0 日後)、`明日`(1 日後)、`明後日`(2 日後)。無ければ記録した日 |
| 時 | `午前` または `午後` を任意で付けた `N時`。`午後` で N が 12 未満なら 12 を足す。N は 0 以上 23 以下 |
| 分 | `M分` または `半`(30 分)。M は 0 以上 59 以下。無ければ 0 分 |
| 時が無い | その日の 23 時 59 分 |

日も時も無ければ `remind_text` と `due_at` は null。範囲外の時や分は無効として null。`due_at` は、ユーザーの timezone の暦日と時刻から UTC の timestamptz に直す。timezone 名が不正なときは `UTC` として扱う。

## 優先度

`calculate_today_priority` は純粋関数。基準は `urgency_score`(null は 0.5)に、期限の補正を足した値。

| 条件 | 補正 |
| --- | --- |
| 期限なし | なし |
| 期限が現在時刻より前(超過) | +0.6 |
| 期限が現在時刻以降で、今日の終わりより前 | +0.4 |

対象は、`completed` の Capture のシナリオで、`done_at` が null、かつ期限が null または今日の終わりより前の行。今日の終わりは、ユーザーの暦日の翌日 0 時。ちょうど翌日 0 時の期限は明日の扱いで、対象外。

並びは次の順で固定する。

1. 優先度の降順
2. `due_at` の昇順(null は最後)
3. `created_at` の昇順
4. `capture_id` の昇順

## 画面

`/captures/today` を足す。Capture 画面と同じ layout、色のトークン、糸と節を使う。ヘッダーに「今日」のリンクを足す。

- 行は、シナリオの title を本文として出す。期限があれば時刻を併記する。押すと詳細へ行く
- 行ごとに「完了にする」ボタンを置く。成功すると行が消える
- 対象が無いときは、糸の最初の節として「今日やることはありません」を出す
- 詳細で `doneAt` があるときは、「完了済み」と「未完了に戻す」を出す
- 取得エラーは `ApiErrorMessage`。未認証は `/login`
- バッジと緊急度の色分けは足さない

色のトークンは [Capture 画面の見た目](./21-capture-visual.md) に合わせる。

## 障害

| 結果 | 扱い |
| --- | --- |
| プロフィールが無い、timezone 名が不正 | `UTC` として扱い、例外にしない |
| Jev の `urgency_score` が範囲外 | `urgency_score` は null で保存し、完了は止めない |
| `limit` が範囲外 | 422 |
| 完了 API で別ユーザー、シナリオ無し | 404 |

## テスト

- 純粋関数だけで、期限の抽出と `due_at`、優先度、日の終わり、並びを検証する。現在時刻は引数で渡す
- 夏時間のある timezone(`America/New_York`)で、23 時間の日と 25 時間の日の終わりが正しい
- `午後 3 時` は 15 時になる
- 超過、今日、期限なし、明日以降、完了済みの組で、返る行と順序を固定する
- 同点の並びが入力の順序に依存しない
- 所有者分離と `done_at` の絞り込みは `integration` にし、通常 pytest から除外する
- 画面の手動確認は、`明日の 9 時に起こして` と `牛乳を買う` が Today に出て、完了で消え、詳細で戻せること

## 実装順

1. 期限の抽出と `due_at`、優先度、日の終わり、並びを純粋関数のテストで GREEN にする。DB も network も使わない
2. migration(`urgency_score`、`due_at`、`done_at`、timezone の既定)と、完了更新で `urgency_score` と `due_at` を書く
3. Today の取得 API と、完了、取り消し API を所有者条件つきで追加する
4. OpenAPI client を再生成する
5. Today 画面、ヘッダーのリンク、完了ボタン、詳細の取り消しを足す
6. API test / worker test / typecheck / lint を GREEN にする

Week 10 では、Today の条件を変えずに朝ダイジェストを足す。
