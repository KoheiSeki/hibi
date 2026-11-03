# Week 6: LLM System Two とハイブリッド分岐

[実装スケジュール](./11-implementation-schedule.md) の Week 6。[Capture 処理](./01-architecture.md#capture処理) の 6 と 7 のうち、聞き返し文の生成までを通す。買い物・予定・支出の実行は Week 7。Week 5 の category、confidence、route、policy version、job 引数は [23-week5-jev-system-one.md](./23-week5-jev-system-one.md) のまま壊さない。

## このステップのゴール

`route` が `clarify` のときだけ LLM に聞き返し文を 1 回作らせ、Capture に保存する。`route` が category と同じ高 confidence では LLM を呼ばず、聞き返し文は空のまま確定する。LLM の timeout と rate limit は Week 4 の job retry に乗せる。不正な structured output は再試行せず、定型文で完了する。

完了条件:

- `route` が `shopping`、`reminder`、`expense`、`note`、`chat` のときは LLM を呼ばない
- `route` が `clarify` のときだけ LLM を 1 回呼ぶ
- LLM 呼び出し回数をテストから読める
- timeout と rate limit は例外になり、3 回目で `failed` になる
- structured output が不正なときは定型文を保存し、`completed` のままにする
- 通常の pytest は LLM を呼ばない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 買い物、予定、支出の実行 | Week 7 のシナリオ |
| 聞き返し文の画面表示 | 保存と契約が先。表示は Week 7 |
| Embedding / RAG / 週次要約 | Week 8 以降 |
| provider の自動切り替え | 障害は retry し、別 provider へは切り替えない |
| category、confidence、policy version の変更 | Week 5 の判定を入力にする |
| job 引数の追加 | `capture_id` と `processing_generation` のまま |

## 挿入位置

`process_capture` で route が決まったあと、`complete_capture_classification` の前に置く。

```text
分類して route を決める
route が clarify でなければ LLM を呼ばない
clarify なら聞き返し文を 1 回作る
分類列と聞き返し文を同じ generation の completed として保存する
```

高 confidence の確定は、新しい status を増やさない。`completed` かつ `clarification_text` が null であることで表す。

## 契約

`app.captures` に `clarification_text text` を追加する。未使用は null。check は、null または 1 文字以上 500 文字以下。

`CaptureResponse.clarificationText` は optional。未設定は null。Web は表示しない。OpenAPI と client は同じ変更で再生成する。

聞き返しの structured output は次だけにする。

```json
{ "question": "いつの予定ですか？" }
```

空文字、500 文字超過、JSON 以外、`question` が無い応答は不正とする。

定型文は `もう少し具体的に教えてください。` 固定。この文を LLM に作らせない。

## Port

SDK 型を service へ漏らさない。

```text
generate_clarification(text, *, category) -> str
```

| 実装 | 用途 |
| --- | --- |
| `FakeClarificationGenerator` | CI。本文に応じた固定の短文を返す。network しない |
| `LlmClarificationGenerator` | 実 LLM。timeout を持つ。API キーが空なら作らない |

service は port だけに依存する。`process_capture_job` は service を呼ぶだけで、LLM SDK を import しない。

呼び出し回数は `hibi.ai.metrics` のカウンタで増やす。fake も clarify 経路で 1 回増やす。高 confidence では増やさない。テストは処理前後の差分を見る。

## 障害

| 結果 | 扱い |
| --- | --- |
| timeout、接続失敗、429、5xx | `ClarificationProviderError` を送出。job が最大 3 回 retry し、最後は `failed` |
| structured output 不正 | 例外にしない。定型文を保存して `completed` |
| route が clarify 以外 | generator を呼ばない |

SDK 側の retry は無効にする。回数の正本は job の 3 回である。

## ファイル

| ファイル | 要点 |
| --- | --- |
| `supabase/migrations/<timestamp>_capture_clarification.sql` | `clarification_text` |
| `apps/api/src/hibi/ai/clarification.py` | port、`ClarificationProviderError`、metric |
| `apps/api/src/hibi/ai/fake_clarification.py` | 固定文を返す fake |
| `apps/api/src/hibi/ai/llm_clarification.py` | structured output の実 adapter。通常 pytest では network しない |
| `apps/api/src/hibi/modules/captures/service.py` | clarify のときだけ生成し、同じ完了更新で保存 |
| `apps/api/src/hibi/modules/captures/repository.py` | 分類列と聞き返し文を同一 UPDATE で書く |
| `packages/api-client` | `clarificationText` を再生成 |

## テスト

- `route=shopping` では generator を呼ばず、`clarification_text` は null、metric は増えない
- `route=clarify` では generator を 1 回呼び、本文を保存し、metric が 1 増える
- timeout と rate limit は例外になり、完了更新は呼ばれない
- 不正な output は定型文で `completed` になり、例外にしない
- 同じ generation の再実行は聞き返し文を二重に作らない
- 実 LLM を呼ぶテストは `integration` にし、通常 pytest から除外する

## 実装順

1. metric と fake generator を、呼び出し回数のテストで GREEN にする
2. migration と、分類列と同じ条件付き UPDATE で `clarification_text` を書く
3. `process_capture` に clarify の分岐を入れる。高 confidence では generator を呼ばない
4. timeout と rate limit を一時障害、不正 output を定型文としてテストする
5. response の optional field と OpenAPI client を再生成する。Web の表示は変えない
6. 実 LLM adapter は port の外側に置き、通常 pytest から除外する
7. API test / worker test / typecheck / lint を GREEN にする

Week 7 では、確定した `shopping`、`reminder`、`expense` の route にシナリオの実行を足す。聞き返し文の生成条件は変えない。
