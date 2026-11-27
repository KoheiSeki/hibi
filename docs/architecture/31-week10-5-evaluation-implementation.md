# Week 10.5: 評価の仕組みと hybrid 検索の実装方針

[Week 10.5 の方針](./30-week10-5-evaluation-and-hybrid-search.md) を、どう実装するかに落とす。タスクの順番とテストは [plan](../superpowers/plans/2026-11-23-week10-5-evaluation-and-hybrid-search.md) にある。この文書は、plan の各 Task で「なぜこの形にするか」「どこで迷いそうか」をまとめる。画面の整理と UI は、別の文書で扱う。

## このステップのゴール

評価を「1 回流して数字を見る道具」ではなく、**同じ条件で何度でも比べられる仕組み**にする。そのために、次の 3 つを守る。

1. **入力を固定する:** 評価データは版つきのファイルで、中身の hash をレポートに残す
2. **実行を記録する:** commit の SHA、モデル、prompt の版、temperature を、結果と一緒に残す
3. **本番と同じ経路を通す:** 分類は `normalize_classification` と `decide_capture_route` を、検索は本番の順位付けの関数を、そのまま呼ぶ。評価のための別実装を作らない

完了条件は [方針](./30-week10-5-evaluation-and-hybrid-search.md#このステップのゴール) のとおり。

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 評価用の DB、Supabase への接続 | 検索も分類も、純粋な関数と adapter だけで評価できる。DB を挟むと、再現性が下がり、遅くなる |
| 評価結果を保存するテーブル、ダッシュボード | レポートを Git で残せば、比較と履歴は足りる。必要になったら Langfuse などを検討する |
| 並列実行の高度な制御(rate limit の自動調整) | `--concurrency` で足りる。429 は失敗として数え、件数で気づく |
| LLM による判定、人手の評価画面 | この週の指標は、すべて正解と比べて機械的に出せる |
| 本番の分類器、検索の既定、embedding の次元の切り替え | 評価の結果を見てから、別の作業で決める |

## 依存の流れ

```text
python -m hibi.evals (CLI)
  ├─ datasets.py   評価データを読む・検証する・hash を取る
  ├─ classification.py
  │    └─ CaptureClassifier (fake / Jev / LlmCaptureClassifier)
  │         → normalize_classification → decide_capture_route   本番と同じ
  ├─ search.py
  │    └─ rank_capture_by_keyword / rank_captures_by_semantic / rank_captures_by_hybrid
  │         ← TextEmbedder (fake / ProviderTextEmbedder)          本番と同じ
  ├─ metrics.py    純粋関数。上の 2 つから呼ばれる
  └─ report.py     metadata、git の状態、Markdown と JSON の書き出し
```

依存は `evals` から業務の層への一方向にする。`modules/` と `ai/` は `evals` を import しない。`evals` は API の起動(`create_app`)や worker からも読まれない。

## 作成・変更ファイル

### 新規

| ファイル | 要点 |
| --- | --- |
| `apps/api/src/hibi/evals/datasets.py` | 評価データの型、読み込み、検証。パスの定数 |
| `apps/api/src/hibi/evals/metrics.py` | 指標。入出力は標準の型だけ |
| `apps/api/src/hibi/evals/report.py` | `RunMetadata`、git の状態、レポートのパスと書き出し |
| `apps/api/src/hibi/evals/classification.py` | 分類の run と集計、Markdown |
| `apps/api/src/hibi/evals/search.py` | 検索の run と集計、Markdown |
| `apps/api/src/hibi/evals/__main__.py` | CLI。引数を読み、上を順に呼ぶだけ |
| `apps/api/src/hibi/ai/usage.py` | `LlmUsage`。呼び出し回数、トークン数、不正な出力の数 |
| `apps/api/src/hibi/ai/llm_classifier.py` | `LlmCaptureClassifier` |
| `docs/ai/evals/capture-classification-v1.jsonl` ほか 2 つ | 評価データ |
| `docs/ai/reports/` | レポート |

### 変更

| ファイル | 要点 |
| --- | --- |
| `apps/api/src/hibi/modules/captures/search.py` | `rank_captures_by_hybrid` と `RRF_K` |
| `apps/api/src/hibi/modules/captures/{types,service,router}.py` | `mode=hybrid` |
| `apps/api/src/hibi/ai/provider_embedder.py` | 次元を引数で受ける。既定は今の 8 |
| `justfile` | `eval-classification`、`eval-search` |

## 実装要点

### 評価データ(`datasets.py`)

- **読み込みと検証を 1 か所にまとめる。** run の途中で不正なデータに気づくと、モデルを呼んだ費用が無駄になる。CLI は、最初に全件を読み、検証を通ってからモデルを呼ぶ
- **エラーは「どのファイルの何行目の、どの項目か」まで出す。** 例: `capture-classification-v1.jsonl line 12: expectedCategory "learning" is not one of chat, expense, note, reminder, shopping`。評価データは手で書くので、直す場所がすぐ分かることが大事
- **hash はファイルのバイト列で取る。** JSON を読み直した値ではなく、ファイルそのもの。空白の違いも「別のデータ」として扱い、レポートの再現条件をはっきりさせる
- **JSON の項目名(camelCase)は、この file の中だけで扱う。** 外へは snake_case の dataclass で渡す。API の schema と同じ考え方
- `REPO_ROOT` は `Path(__file__).resolve().parents[5]`。`fake_classifier.py` と同じ深さなので、同じ式になる

### 指標(`metrics.py`)

- **すべて純粋関数にする。** 入力は `Sequence[str]`、`Sequence[bool]`、`Sequence[float]`、`AbstractSet[str]` だけ。dataclass や分類器を知らない。テストを手計算で書けるようにするため
- **分母が 0 のときは 0.0 を返し、例外にしない。** 件数の少ない category や、正解の無い質問があっても、レポート全体が止まらないように
- **macro-F1 は、正解に 1 件以上ある category だけで平均する。** 評価データに無い category を 0 として混ぜると、データの偏りが指標に出てしまう
- **calibration の区間は Decimal で決める。** `0.7 * 10` は浮動小数で `7.000000000000001` になり、たまたま正しい区間に入るが、`0.3` などで境界がずれることがある。`Decimal(str(c)) * 10` の整数部で決める。1.0 は最後の区間(0.9〜1.0)に入れる
- **percentile は nearest-rank 法。** 線形補間より説明しやすく、件数が少ないときに、実在しない値を出さない
- **nDCG の関連は 2 値。** 段階を付けると、評価データを作る手間が大きく増える。v1 は 2 値で始め、必要なら v2 で段階を足す

### 呼び出しの記録(`ai/usage.py`)

`LlmUsage` は、分類器と run の両方が同じ 1 つを持つ、可変の入れ物。

- **トークン数は、1 回でも不明が混ざったら、以後は None にする。** 手元のサーバーは usage を返さないことがある。0 と足すと「費用 0」と誤読される。合計が出せないなら、出さない
- **不正な出力の数(`invalid_outputs`)を数える。** LLM の分類器は、不正な出力を例外にせず `unknown` にする(本番の扱いと同じ)。そのため、正解率だけを見ると「間違えた」のか「形を守れなかった」のかが分からない。別に数える
- 既存の `record_llm_call()`(テストで LLM の呼び出し回数を見るための global)は、そのまま呼ぶ。評価用の `LlmUsage` とは別物で、置き換えない

### レポート(`report.py`)

- **ファイル名は `YYYY-MM-DD-<suite>-<label>`。** 同じ日に同じ label で再実行したら、`-2`、`-3` を付ける。前の結果を消さないため
- **base URL は host と port だけを残す。** `urlsplit(url).hostname` と `port` から組み立てる。`https://user:secret@...` のような URL でも、キーやパスがレポートに出ない
- **git の状態は、SHA と「未 commit の変更があったか」の 2 つ。** 変更があった run は、Markdown に `uncommitted changes` と明記する。比較に使ってよいかを、読む人が判断できるように
- **JSON は `{"metadata", "metrics", "cases"}` の 3 つに分ける。** cases にはケースごとの予測を全部入れる。あとで「どのケースを間違えたか」を、run をやり直さずに調べられる

レポートの Markdown は次の形にする(英語)。

```markdown
# Classification evaluation: local-qwen2.5-7b

## Run
| Item | Value |
| --- | --- |
| Started at | 2026-12-05T21:10:00+09:00 |
| Commit | 1a2b3c4 (uncommitted changes) |
| Dataset | docs/ai/evals/capture-classification-v1.jsonl (sha256: 9f86…) |
| Implementation | llm |
| Model | mlx-community/Qwen2.5-7B-Instruct-4bit @ localhost:8080 |
| Prompt version | capture-llm-classify-v1 |
| Temperature | 0.0 |
| Repeats | 1 |

## Summary
| Metric | Value |
| --- | --- |
| Accuracy | 0.82 |
| Macro-F1 | 0.79 |
| Clarification F1 | 0.64 |
| Failures | 0 |
| Disputed (excluded) | 2 |

## Per category
## Confusion matrix
## Clarification
## Calibration
## By tag
## Latency and cost
```

数値は形を示すための例で、実測値ではない。

### 分類の run(`classification.py`)

- **1 ケースの流れは、本番の `CaptureService.process_capture` と同じ順にする。** `classify_capture(raw_text, question_version=CAPTURE_QUESTION_VERSION)` → `normalize_classification` → `decide_capture_route`。評価で良い結果が出ても、本番と経路が違えば意味がない
- **並列は `asyncio.Semaphore` で絞り、`asyncio.gather` で全ケースを流す。** 結果はケースの順に並べ直す(`gather` は入力の順を保つ)。外部 API の rate limit と、手元のモデルのメモリを守るため、既定は 4、`--base-url` があるときは 1
- **捕まえる例外は `ClassificationTimeoutError` だけ。** それ以外(実装の誤り)は上へ流して run を止める。バグを「失敗 1 件」として数えると、指標が静かに壊れる
- **失敗の扱い:**

| 指標 | 失敗(timeout)の扱い | 理由 |
| --- | --- | --- |
| 正解率、category ごとの指標、混同行列 | 不正解として数える(予測は `error`) | 利用者から見ると、仕分けられなかったことに変わりはない |
| 聞き返しの precision / recall | 除く | 判断そのものが無い |
| calibration | 除く | confidence が無い |

- **`disputed` のケースは、指標から外して件数だけ出す。** 人が見ても正解が決まらないケースで、モデルを責めないため
- **repeats が 2 以上のとき:** 正解率、macro-F1、聞き返しの F1 だけを repeat ごとに計算して、平均と標準偏差を出す。混同行列などの詳細は、全 repeat の予測を合わせて作る。temperature 0 でも、モデルやサーバーによって出力が揺れることがあり、その揺れの大きさ自体が比べる材料になる

### LLM の分類器(`ai/llm_classifier.py`)

- **`CaptureClassifier` の Protocol をそのまま満たす。** 評価の runner も、将来の本番の切り替えも、Jev と同じ差し込み口で扱える
- **client と分類器を分ける**(`llm_clarification.py` と同じ形)。client は「OpenAI 互換の API を呼び、文字列とトークン数を返す」だけ。分類器は「JSON を読み、`Classification` にする」だけ。テストは偽の client で、ネットワークなしに書ける
- **出力の読み方:**

| 出力 | 扱い |
| --- | --- |
| 正しい JSON、値が範囲内 | そのまま `Classification` にする。confidence は `Decimal(str(value))` |
| JSON として読めない、項目が欠ける、confidence や urgency が 0〜1 の外 | `category="unknown"`、`confidence=0` を返し、`invalid_outputs` を 1 増やす |
| 許可されていない category(`learning` など) | そのまま返す。`normalize_classification` が chat の確信度 0 に置き換える(本番と同じ) |
| timeout、接続の失敗、429、5xx | `ClassificationTimeoutError` |

- **prompt は版で固定する。** 文を 1 文字でも変えたら、`CAPTURE_LLM_CLASSIFY_PROMPT_VERSION` を上げる。レポートの比較が「同じ prompt での比較」であることを保証するため。prompt の本文は plan の Task 5 にある
- **category の説明は、Jev の criteria と同じ文にする。** モデルの違いと、指示の違いを混ぜないため
- **confidence はモデルの自己申告で、Jev の confidence とは性質が違う。** 閾値 0.70 でそのまま比べてよいかは、calibration の表で確かめる。LLM は高い confidence を出しがちで、閾値の手前で止まらないことが多い。それ自体が、この週に確かめたいことの 1 つ

### 手元のモデルの動かし方

M4 / 16GB では、4bit の 7B モデルが目安。最初は Qwen2.5-7B-Instruct の 4bit 版を使う(日本語に強く、JSON の指示に従いやすい)。

```bash
# 別の端末でサーバーを起動する(OpenAI 互換。初回はモデルをダウンロードする)
uv tool run --from mlx-lm mlx_lm.server --model mlx-community/Qwen2.5-7B-Instruct-4bit --port 8080

# まず 5 件で、1 件あたりの時間を確かめる
just eval-classification --classifier llm \
  --base-url http://localhost:8080/v1 \
  --model mlx-community/Qwen2.5-7B-Instruct-4bit \
  --label local-qwen2.5-7b --max-cases 5
```

- `mlx_lm.server` が `response_format` の JSON モードに対応していない場合も、prompt で JSON を求めているので動く。形を守れなかった件数は `invalid_outputs` に出る
- JSON の形を強く守らせたいときは、llama.cpp の `llama-server`(JSON schema の制約に対応)に替えて比べてもよい。サーバーを替えたら、label を変えて別のレポートにする
- 速さとメモリは、モデルと設定で大きく変わる。数字は実測してからレポートに書く

### hybrid 検索(`modules/captures/search.py`)

- **既存の 2 つの関数を呼んで、順位だけを使う。** スコアそのもの(TF-IDF とコサイン類似度)は尺度が違うので、足し合わせない。RRF は順位だけを使うので、尺度をそろえる必要がない
- **`score(d) = Σ 1 / (60 + rank(d))`、rank は 1 始まり。** `k = 60` は RRF の論文で使われ、広く使われている値。小さいほど上位を重く見る。v1 は固定し、変えるなら評価で決める
- **片方にしか出ない文書も残す。** キーワードでしか見つからない記録(固有名詞など)と、意味でしか見つからない記録(言い換え)の両方を拾うことが、hybrid の目的
- **所有者と状態の絞り込み、類似度 0 の除外は、既存の関数に任せる。** 同じ規則を 2 か所に書かない
- API は `mode=hybrid` を受け付けるだけ。既定は `keyword` のまま、画面も変えない。既定を変えるかは、評価の結果で決める

### 検索の run(`evals/search.py`)

- **DB を使わず、評価データを `SearchDocument` に変えて、本番の関数に渡す。** capture ID は `uuid5(NAMESPACE_URL, doc_id)` で決める。毎回同じ ID になり、同点の並び(ID 順)も再現する。user は `UUID(int=1)`、status は `completed`
- **文書の embedding は、run の最初に 1 回だけ作る。** 本番でも、記録の embedding は保存済みで、検索のたびに作るのは質問だけ。latency の比較を本番に近づけるため
- **latency は質問 1 件ごと、mode ごとに測る。** semantic と hybrid には、質問の embedding を作る時間が入る。ここが、キーワード検索との速さの差の大部分になる
- **embedding の次元は `--dimensions` で変えられる。** 本番の `vector(8)` は、Week 8 で fake と揃えるために決めた値で、実際のモデルの品質には小さい。DB は変えずに、まず 8 次元と 256 次元の差を測る。差が大きければ、migration を伴う別の作業として提案する

### CLI(`evals/__main__.py`)

```text
python -m hibi.evals classification --classifier {fake,jev,llm} [--base-url URL] [--model NAME]
    [--label L] [--repeats N] [--max-cases N] [--concurrency N] [--dataset PATH] [--reports-dir PATH]

python -m hibi.evals search --embedder {fake,provider} [--dimensions N]
    [--label L] [--corpus PATH] [--queries PATH] [--reports-dir PATH]
```

処理の順番は次のとおり。順番に意味がある。

1. **評価データを読む:** 不正なら、モデルを呼ぶ前に止まる
2. **キーを確かめる:** 無ければ、モデルを呼ぶ前に止まる。`--base-url` を指定した LLM だけは、キーが空でも動く(手元のサーバーはキーを見ない)
3. **呼び出す回数を表示する:** 「ケース数 × repeats」。費用の見積もりの代わり
4. **run する**
5. **レポートを書き、2 つのパスを表示する**

終了コードは、0 が完了、2 が引数・評価データ・キーの不備、130 が中断(Ctrl-C)。中断したら、何も書かない。途中までの結果を、正しい結果のように残さないため。

CLI は引数を読んで、上の部品を順に呼ぶだけにする。判断はすべて部品の側に置き、テストは部品の単位で書く。

## 評価データの書き方

評価の質は、評価データの質で決まる。次の方針で作る。

### 分類

- **本当に記録しそうな文にする。** 「牛乳を買う」のような典型だけでなく、「牛乳きれてた」「ぎゅうにゅう 2 本」のような、実際の打ち方を入れる
- **tags で難しさを分ける。** tags ごとの正解率が、モデルの弱点の地図になる

| tag | 例 | 見たいこと |
| --- | --- | --- |
| `basic` | 牛乳を買う | 典型を落とさないか |
| `relative-date` | 来週の火曜に歯医者 | 日付の表現を reminder と読めるか |
| `amount` | コンビニ 680、昼 ¥1,200 | 金額の書き方の揺れ |
| `colloquial` | 牛乳きれてた、あとでみる | 話し言葉、省略 |
| `notation` | ギュウニュウ、ｌｕｎｃｈ ９８０円 | かな・カナ・全角半角 |
| `mixed` | 明日 1500 円の本を買う | 2 つの category にまたがる。正解は「主な目的」で決め、迷ったら `disputed` |
| `ambiguous` | あれやっといて | 聞き返すべき(`shouldClarify: true`) |

- **`shouldClarify: true` の正解の category は、人が一番ありそうだと思うもの。** 分類の指標と、聞き返しの指標を、同じケースで別々に測るため
- **迷ったら `disputed`。** 正解の決まらないケースで、モデルを採点しない。ただし、`disputed` が全体の 1 割を超えたら、category の定義が曖昧な合図なので、記録しておく

### 検索

- **文書は、1 人のユーザーが数週間に記録しそうな内容にする。** category が混ざり、似た記録(牛乳を買う、牛乳を飲んだ)が並ぶ状態にする。似た記録が無いと、順位の差が出ない
- **質問は、実際に探すときの言い方にする。** 記録をそのまま打つ(`exact`)より、「ミルク」「乳製品」「先週の飲み物」のような探し方が多い
- **正解は「その質問で見つかってほしい記録」をすべて。** 1 件に絞らない。Recall が意味を持つように

## テスト方針(このステップ)

- **指標は、手で計算できる小さな入力で、値を固定して確かめる。** 期待値は、テストの中に計算式で書く(`(2 / 3 + 2 / 3 + 1.0) / 3` など)。どう求めたかが読めるように
- **run は stub の分類器と stub の clock で確かめる。** 時間とネットワークに依存しない。stub の分類器は、本文から答えを引く dict と、`TIMEOUT` で例外を投げる分岐だけを持つ
- **CLI は `main(argv)` を直接呼んで確かめる。** subprocess を使わない。出力先は `tmp_path`
- **外部の API を呼ぶテストは書かない。** 実モデルの確認は、レポートを作ること自体が確認になる
- **評価データのファイルも、テストで形と件数を確かめる。** 誰かがデータを壊したら、通常の pytest で気づける

## 実装順

plan の Task 1〜8 のとおり。要点は次の 3 つ。

1. 評価データの読み込み → 分類のデータ → 指標 → 分類の run の順に作り、**fake と Jev の baseline を先に取る**。LLM の分類器は、比べる相手ができてから足す
2. hybrid 検索は、検索の評価の前に作る。評価の run は、本番の 3 つの関数を呼ぶだけにするため
3. 最後に、結果と判断を方針の文書の末尾に記録する。数字が出てから結論を書き、結論から数字を選ばない

## 次ステップ(画面の整理と UI)

画面の整理と UI の文書を作る。検索の既定を hybrid に変えるかは、このステップの結果を見て、検索欄の見直しと一緒に決める。

## 関連

- [Week 10.5 の方針](./30-week10-5-evaluation-and-hybrid-search.md)
- [plan](../superpowers/plans/2026-11-23-week10-5-evaluation-and-hybrid-search.md)
- [Week 5: Jev の分類](./23-week5-jev-system-one.md)
- [Week 6: LLM](./24-week6-llm-system-two.md)
- [Week 8: 検索](./26-week8-search.md)
- [現状アーキテクチャ](./29-current-architecture.md)
