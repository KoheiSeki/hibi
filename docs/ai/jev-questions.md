# Capture 分類の質問

Week 5 の Jev へ渡す質問の正本。policy version は `capture-route-v1`。route はこの質問の出力に含めない。

question_version: capture-classify-v1

## 質問

次の一文を、許可された category のどれか 1 つに分類する。説明文は返さない。

許可する category:

| category | 意味 |
| --- | --- |
| `shopping` | 買う、注文する、在庫を補う |
| `reminder` | 時刻や日付を伴う予定、想起 |
| `expense` | 金額を伴う支出の記録 |
| `note` | 後で読む、保管する情報 |
| `chat` | 会話、感想、上のどれにも決まらない雑談 |

出力:

| field | 型 | 制約 |
| --- | --- | --- |
| `category` | string | 上の 5 つのいずれか |
| `confidence` | number | `0` 以上 `1` 以下 |
| `urgencyScore` | number | `0` 以上 `1` 以下。Week 5 の policy は無視し、保存する urgency は `normal` |

`route`、聞き返し文、要約は返さない。

## Fake の規則

`FakeCaptureClassifier` は network を使わない。`docs/ai/evals/capture-route-v1.jsonl` の `rawText` と完全一致した行の `category` と `confidence` を返す。前後の空白を足した文字列は一致させない。`urgencyScore` は常に `0.5`。`question_version` は `capture-classify-v1`。

一致しない文章は `category=chat`、`confidence=0.5`、`urgencyScore=0.5` を返す。route は返さない。`decide_capture_route` が、confidence `0.70` 以上なら category を route にし、未満なら `clarify` にする。

質問文または許可 category を変えるときは、`question_version` を上げて dataset を新しいファイルに分ける。`capture-classify-v1` の行は書き換えない。
