# Week 8: 検索

[実装スケジュール](./11-implementation-schedule.md) の Week 8。[Capture 処理](./01-architecture.md#capture処理) の 7 のうち、完了した記録の検索までを通す。聞き返し、シナリオの確認、job 引数は [25-week7-daily-scenarios.md](./25-week7-daily-scenarios.md) のまま壊さない。

## このステップのゴール

`completed` の Capture を、所有者の中だけで検索できる。意味検索は embedding の近さ、キーワード検索は本文の語の重なりで選ぶ。検索結果に別ユーザーの行は出ない。通常の pytest は embedding API を呼ばない。

完了条件:

- `牛乳を買う` は、キーワード `牛乳` で見つかる
- `あとで読む記事` は、キーワード `記事` で見つかる
- `ミルク` は、意味検索では `牛乳を買う` に近く、キーワード検索では見つからない
- `ランチ` は、キーワード検索では `ランチ 1200 円` に当たり、意味検索の上位は `牛乳を買う` にならない
- 別ユーザーの同じ本文は、どちらの検索にも出ない
- `pending`、`processing`、`failed` は検索対象にしない
- embedding の model、dimensions、version を行に残す
- 通常の pytest は Jev、LLM、embedding API を呼ばない

## やらないこと

| 先送り | 理由 |
| --- | --- |
| 検索結果を使った回答生成 | Week 10 の要約まで。この週の RAG は検索で記録を取り出すところまで |
| embedding の自動 backfill | version 列だけ残す。再生成ジョブは後続 |
| HNSW など近似近傍 index | 件数が小さい。計測前に足さない |
| Today の優先度 | Week 9 |
| 検索の高度な filter、日付、route 絞り込み | 遅延時に削る対象 |
| 一覧のバッジと色分け | [Capture 画面の見た目](./21-capture-visual.md) を壊さない |
| job 引数の追加 | `capture_id` と `processing_generation` のまま |

## 挿入位置

`process_capture` で分類とシナリオを保存したあと、同じ generation の `completed` に対して embedding を 1 回書く。検索 API はその行を読むだけで、リクエストのたびに embedding を作り直さない。

```text
分類して route を決める
clarify なら聞き返し文を作る
shopping、reminder、expense なら提案を作る
completed として保存する
同じ本文の embedding が無ければ 1 回作って保存する
```

検索は job の外に置く。`GET /api/v1/captures/search` が、検証済みの `user_id` だけでキーワード検索か意味検索を選ぶ。

## 契約

`app.capture_embeddings` を追加する。`capture_id` が主キーで、`app.captures` を参照する。1 Capture につき 1 行まで。`vector` 拡張を有効にする。

| 列 | 内容 |
| --- | --- |
| `capture_id` | Capture の id |
| `user_id` | 所有者。Capture と同じ値 |
| `content_text` | embedding した本文。1 文字以上 2000 文字以下 |
| `content_hash` | 本文の sha256。同じ hash なら作り直さない |
| `embedding` | `vector`。次元は `embedding_dimensions` と一致 |
| `embedding_model` | モデル名。fake は `capture-embed-fake-v1` |
| `embedding_dimensions` | 次元数。1 以上 |
| `embedding_version` | `capture-embed-v1` |
| `created_at`、`updated_at` | timestamptz |

距離は cosine に固定する。`user_id` の btree index は付ける。HNSW は付けない。権限は `app.captures` と同じで、`anon` と `authenticated` からは剥奪し、`hibi_runtime` に CRUD を渡す。

検索は `GET /api/v1/captures/search`。`q` は 1 文字以上 200 文字以下。`mode` は `keyword` または `semantic`。未指定は `keyword`。成功は 200 で、既存の Capture 一覧と同じ要素を、近い順に最大 20 件返す。`scenario` は一覧と同じく載せてよい。0 件は空配列で、404 にはしない。`q` が空、または `mode` が不正なら 422。

OpenAPI と client は同じ変更で再生成する。path は `/{capture_id}` より前に登録する。

## Port

SDK 型を service へ漏らさない。

```text
embed_text(text) -> Embedding
```

`Embedding` は `vector`、`model`、`dimensions`、`version` を持つ。

| 実装 | 用途 |
| --- | --- |
| `FakeTextEmbedder` | CI。評価用の固定ベクトルを返す。network しない |
| `ProviderTextEmbedder` | 実 embedding。API キーが空なら作らない |

fake の固定ベクトルは次だけにする。次元は 8。それ以外の本文は、語を並べた hash から同じ次元のベクトルを作る。

| 本文 | 近い相手 |
| --- | --- |
| `牛乳を買う`、`ミルク` | 互いに近い |
| `あとで読む記事`、`読みもの` | 互いに近い |
| `ランチ 1200 円` | 上の 2 組からは遠い |

キーワード検索は TF-IDF の語の重なりにする。分割は空白と、ひらがな・カタカナ・漢字の連続とする。`牛乳` は `牛乳を買う` に当たり、`ミルク` には当たらない。`記事` は `あとで読む記事` に当たる。

意味検索は、クエリを同じ embedder でベクトル化し、同じ `user_id` かつ同じ `embedding_version` の行だけを cosine 距離で並べる。

## 画面

一覧の糸と節は残す。検索欄は日付の下、糸の上に置く。

```text
10月18日 日
┌ 記録を検索            ┐
│ キーワード / 意味      │
● 14:02  牛乳を買う
```

- 未入力の一覧は、今までの時刻順のまま
- 検索中は「検索しています」
- 0 件は糸の上に「見つかりませんでした」
- 結果の行は、今の一覧行と同じ。押すと詳細へ行く
- バッジと処理状態の色分けは足さない

色のトークンは [Capture 画面の見た目](./21-capture-visual.md) に合わせる。

## 障害

| 結果 | 扱い |
| --- | --- |
| embedding の timeout、接続失敗、429、5xx | 例外にして job の retry に乗せる。3 回目で Capture は `failed` |
| 本文が空 | embedding を呼ばない |
| 同じ `content_hash` が既にある | embedding を呼ばない |
| 検索の `q` が空、`mode` が不正 | 422。retry しない |

SDK 側の retry は無効にする。回数の正本は job の 3 回である。

## テスト

- fake のベクトルで、`ミルク` は `牛乳を買う` に近く、`ランチ 1200 円` には近くない
- キーワード検索で、`牛乳` は `牛乳を買う` に当たり、`ミルク` は当たらない
- `記事` は `あとで読む記事` に当たる
- `pending` の行はどちらにも出ない
- 別ユーザーの行はどちらにも出ない
- 同じ本文の再処理では embedder の呼び出しが増えない
- 実 embedding を呼ぶテストは `integration` にし、通常 pytest から除外する
- 画面の手動確認は、検索欄から `牛乳` で買い物の行が出て、`ミルク` は意味検索のときだけ出ること

## 実装順

1. fake embedder と、キーワード検索、意味検索の順位をテストで GREEN にする。DB も network も使わない
2. migration と、完了更新と同じ条件で embedding を 1 行書く。同じ hash は書き直さない
3. `process_capture` から embedder を呼ぶ。キーが空なら fake を使う
4. 検索 API を所有者条件つきで追加し、OpenAPI client を再生成する
5. 一覧の上に検索欄を足す。結果は今の行を使う
6. API test / worker test / typecheck / lint を GREEN にする

Week 9 では、検索条件を変えずに Today の優先度を足す。
