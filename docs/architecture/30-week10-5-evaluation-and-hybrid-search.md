# Week 10.5: 評価の仕組みと hybrid 検索

[実装スケジュール](./11-implementation-schedule.md) の Week 10.5 のうち、評価と検索の部分。画面の整理と UI は、別の文書で決める。

## このステップのゴール

AI の結果を「処理が成功したか」ではなく、品質として測れるようにする。分類と route の品質、検索の品質を、版の決まった評価データで測り、結果をレポートとして残す。同じ方法で、Jev、商用の LLM、手元で動かす open-weight モデルを比べられるようにする。検索には、キーワードと意味検索の順位をまとめる hybrid を足し、3 方式を数字で比べる。

デプロイの前に baseline を取っておくのは、本番化のあとの改善(チャット、Memory、serving)を、すべて同じ物差しで比べるため。

完了条件:

- 分類の評価データ(60 件以上)と、検索の評価データ(文書 60 件以上、質問 30 件以上)が、版つきで `docs/ai/evals/` にある
- `just eval-classification` と `just eval-search` が、指標、版、費用を含むレポートを `docs/ai/reports/` に書く
- Jev の baseline レポートがある。商用の LLM と、手元の open-weight モデル 1 つのレポートがある
- 検索の 3 方式(keyword、semantic、hybrid)の比較レポートがあり、既定の方式を数字で説明できる
- 通常の pytest と CI は、外部の API を呼ばない

## やらないこと

| 項目 | 理由 |
| --- | --- |
| 本番の分類器を LLM に切り替える | 評価の結果を見てから決める。この週は測るだけ |
| 検索の候補の絞り込みを DB(pgvector、pg_bigm)へ移す | 件数が少ないうちは Python 側で足りる。移すかは計測で決める |
| reranker、LLM による判定(LLM judge) | まず指標で測れるものから始める。Phase 14 の後 |
| CI で実モデルの評価を回す | 費用と、結果の揺れのため。手で実行する |
| 画面の変更(検索欄に hybrid を出すなど) | 画面の整理の文書でまとめて決める |
| カテゴリを増やす | 仕様の変更になる。評価で弱点が分かってから決める |

## 用語

| 用語 | 意味 |
| --- | --- |
| 評価データ | 入力と正解の組。JSON Lines で、ファイル名に版を付ける |
| suite | 評価の種類。`classification` と `search` の 2 つ |
| run | 1 回の評価の実行。suite、評価する実装、評価データの版を決めて、全件を流す |
| レポート | run の結果。人が読む Markdown と、機械が読む JSON の 2 つ |

## 評価データ

`docs/ai/evals/` に置き、Git で版を管理する。中身を変えたら、ファイル名の版を上げる(`-v1` → `-v2`)。既存の `capture-route-v1.jsonl` は、fake の分類器とテストが使う表なので、そのまま残し、評価には使わない。

### 分類: `capture-classification-v1.jsonl`

```json
{"caseId": "cls-001", "rawText": "牛乳を買う", "expectedCategory": "shopping", "shouldClarify": false, "tags": ["basic"]}
{"caseId": "cls-061", "rawText": "あれやっといて", "expectedCategory": "chat", "shouldClarify": true, "tags": ["ambiguous"]}
```

| 項目 | 意味 |
| --- | --- |
| `caseId` | 一意な ID。変えない |
| `rawText` | 記録の本文 |
| `expectedCategory` | 正解の category。`shopping`、`reminder`、`expense`、`note`、`chat` のどれか |
| `shouldClarify` | 人が見て、聞き返すべき曖昧な記録なら true |
| `tags` | 難しさの種類。集計を分けるのに使う |

構成:

- 5 つの category を 10 件以上ずつ。`shouldClarify: true` を 10 件以上
- tags の例: `basic`、`relative-date`(明日、来週)、`amount`(金額の書き方の揺れ)、`colloquial`(話し言葉、省略)、`notation`(かな、カナ、漢字、全角半角の揺れ)、`mixed`(2 つの category にまたがる)、`ambiguous`
- 正解は、Claude が案を作り、ユーザーが全件を確かめて確定する。迷った例は、迷った理由を `tags` に `disputed` として残し、集計から外せるようにする

### 検索: `capture-search-corpus-v1.jsonl` と `capture-search-queries-v1.jsonl`

```json
{"docId": "doc-001", "text": "牛乳を買う"}
```

```json
{"queryId": "q-001", "query": "ミルク", "relevantDocIds": ["doc-001"], "tags": ["synonym"]}
```

- 文書は、実際に記録しそうな本文を 60 件以上。5 つの category にまたがる
- 質問は 30 件以上。tags で `exact`(同じ語)、`synonym`(言い換え)、`paraphrase`(意味だけ近い)、`notation`(表記の揺れ)を分ける
- 正解は、関連する文書の ID の集合。関連の強さは段階を付けず、関連する / しないの 2 値にする

## 評価の runner

`apps/api/src/hibi/evals/` に置く。Hibi の adapter と policy をそのまま使うため、API と同じパッケージに入れる。業務の層からは import しない(依存は evals から業務の層への一方向)。

```text
hibi/evals/
  __main__.py        CLI。suite と実装を選んで run する
  datasets.py        評価データを読み、形を確かめる
  classification.py  分類の run
  search.py          検索の run
  metrics.py         指標の計算。純粋な関数だけ
  report.py          Markdown と JSON を書く
```

### 実行

```bash
just eval-classification --classifier jev
just eval-classification --classifier llm --base-url http://localhost:8080/v1 --model mlx-community/Qwen2.5-7B-Instruct-4bit --label local-qwen7b
just eval-search --embedder provider
```

- `--classifier` は `fake`、`jev`、`llm`。`--embedder` は `fake`、`provider`
- `llm` の接続先は、引数の `--base-url` と `--model` が設定値(`HIBI_OPEN_AI_*`)より優先する。API キーは設定値から読み、レポートには書かない
- `--repeats N` で同じ評価を N 回流し、指標を平均と標準偏差で出す。既定は 1
- `--max-cases N` で件数を絞れる。始める前に、呼び出す回数を表示する
- 実行中の失敗(timeout、不正な出力)は再試行せず、そのケースを「失敗」として数える。失敗の件数もレポートに出す
- 同時に呼ぶ数は既定 4。`--concurrency` で変える(手元のモデルは 1 が安全)

### 分類の run が測るもの

各ケースで `classify_capture` を呼び、`normalize_classification` と `decide_capture_route` を本番と同じ順で通す。

| 指標 | 内容 |
| --- | --- |
| 正解率 | category の一致率 |
| macro-F1 | category ごとの F1 の平均。件数の少ない category も同じ重みで見る |
| category ごとの precision / recall / F1 | どの category が弱いか |
| 混同行列 | どれをどれと間違えたか |
| 聞き返しの precision / recall | route が `clarify` になったことと、`shouldClarify` の一致 |
| calibration | confidence を 0.1 刻みの区間に分け、区間ごとの正解率と件数を並べる。route の閾値(0.70)が妥当かを見る |
| tags ごとの正解率 | 難しさの種類ごとの弱点 |
| latency | p50、p95 |
| 費用 | LLM のトークン数(入力、出力)。Jev は呼び出し回数 |
| 失敗 | timeout、不正な出力の件数 |

### 検索の run が測るもの

コーパスを `SearchDocument` に変え、本番と同じ順位付けの関数を呼ぶ。DB は使わない。意味検索の embedding は、run の最初にコーパス全体を 1 回作る。

本番の embedding は `vector(8)` で、実際のモデルの品質には小さい。評価では、`--dimensions` で次元を変えて(例: 256)、本番の 8 次元との差を測る。DB と本番の次元は、この週は変えない。

| 指標 | 内容 |
| --- | --- |
| Recall@5、Recall@10 | 正解が上位に入る割合 |
| MRR | 最初の正解の順位の逆数の平均 |
| nDCG@5 | 順位と関連の両方を見る(関連は 2 値) |
| tags ごとの Recall@5 | 言い換えや表記揺れへの強さ |
| latency | 質問 1 件あたりの p50、p95(質問の embedding を含む) |

### レポート

`docs/ai/reports/YYYY-MM-DD-<suite>-<label>.md` と、同じ名前の `.json`。`label` の既定は実装の名前。

どちらにも、次の情報を必ず残す。後で同じ run を再現できるようにするため。

- 実行日時、git の commit SHA、作業ツリーに未 commit の変更があったか
- 評価データのファイル名と、中身の SHA-256
- 実装の名前、model、base URL の host(キーは書かない)、question / prompt の版、temperature、repeats
- 指標と、ケースごとの予測(JSON だけ)

レポートの本文は英語で書く。ポートフォリオとしても読まれる前提のため。

## LLM の分類器

`hibi/ai/llm_classifier.py` に `LlmCaptureClassifier` を足す。`CaptureClassifier` の Protocol を満たし、OpenAI 互換の chat completions を JSON の出力で呼ぶ。

- 出力は `{"category": "...", "confidence": 0.0〜1.0, "urgency": 0.0〜1.0}`。Pydantic で読み、不正なら例外にせず `category: "unknown"`、`confidence: 0` を返す。`normalize_classification` が chat の確信度 0 に置き換え、route は `clarify` になる(本番の扱いと同じ)
- timeout、接続、rate limit、5xx は `ClassificationTimeoutError` にする(Jev と同じ)
- prompt の版は `capture-llm-classify-v1`。`question_version` は引数をそのまま返す
- temperature は 0
- トークン数を返せるよう、client は usage を一緒に返す。`record_llm_call()` も呼ぶ
- この週は、`hibi/ai/factory.py` に繋がない。評価の runner だけが使う。本番を切り替えるかは、レポートを見て別に決める

LLM が出す confidence は、モデル自身の申告で、Jev の confidence と性質が違う。そのまま閾値 0.70 で比べてよいかは、calibration の表で確かめる。この確認自体が、この週の成果の 1 つ。

## hybrid 検索

`hibi/modules/captures/search.py` に `rank_captures_by_hybrid` を足す。

- キーワードと意味検索の順位を、Reciprocal Rank Fusion でまとめる。`score(d) = Σ 1 / (k + rank(d))`、`k = 60`、rank は 1 始まり
- 片方にしか出ない文書は、出た方の項だけを足す
- 同点は capture ID の昇順(既存の 2 方式と同じ)
- mode に `hybrid` を足す(`CAPTURE_SEARCH_MODE_HYBRID`)。API の `mode` で選べる。既定は `keyword` のまま変えない
- `just openapi` で client を再生成する。画面は変えない

既定の方式を `hybrid` に変えるかは、比較レポートで決める。`hybrid` の MRR と Recall@5 が、どちらも 2 方式以上なら変える。変えるのは、画面の整理の作業で検索欄と一緒に行う。

## 障害

| 起きること | 扱い |
| --- | --- |
| 評価データの形が不正 | 最初に全件を確かめ、どの行のどの項目かを示して止まる。1 件も呼ばない |
| モデルの timeout、不正な出力 | そのケースを失敗として数え、続ける |
| 途中で止めた(Ctrl-C) | レポートは書かない。部分的な結果を正しい結果に見せないため |
| API キーが無い | `jev`、`llm`、`provider` は始める前に止まる。`fake` は動く |

## テスト

通常の pytest に足す。どれも外部の API を呼ばない。

- `metrics.py`: 正解率、macro-F1、precision / recall、混同行列、calibration の区間、Recall@K、MRR、nDCG。手で計算できる小さな入力で確かめる。0 件や、正解が無いときの割り算も
- `datasets.py`: 正しいファイルを読める。不正な category、重複した ID、存在しない `relevantDocIds` を、行番号つきで拒む
- `rank_captures_by_hybrid`: 両方に出る文書が上に来る。片方だけの文書も残る。同点は ID 順。他人の行と未完了の行は出ない
- `LlmCaptureClassifier`: 偽の client で、正しい出力、不正な JSON、範囲外の confidence、例外の変換、usage の受け渡し
- runner: fake の分類器と fake の embedder で run し、レポートの必須項目(SHA、データの hash、指標)が出る
- 検索の API: `mode=hybrid` を受け付ける

## 実装順

1. 評価データの形と読み込み(`datasets.py`)。分類の評価データの案を作り、ユーザーが確定する
2. 指標(`metrics.py`)
3. 分類の run とレポート。fake と Jev で baseline を取る
4. `LlmCaptureClassifier`。商用の LLM と、手元の open-weight モデルで run する
5. 検索の評価データ、`rank_captures_by_hybrid`、`mode=hybrid`、検索の run
6. 3 方式の比較レポートと、既定の方式の判断を、この文書の末尾に記録する
