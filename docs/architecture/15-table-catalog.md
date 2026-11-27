# テーブル定義

`app` schema の業務 table を、table 単位でまとめた定義書です。SQL の正は `supabase/migrations` です。関係の俯瞰は [ER図](./14-er.md) を見ます。

ER だけでは check、unique、index、権限が追いづらいため、table を追加したらこの文書も同じ PR で更新します。

## 共通規則

- 業務 table はすべて `app` に置く。本番も `app`（[ER図](./14-er.md)）
- `public` / `graphql_public` には業務 table を作らない
- `anon` / `authenticated` からは `REVOKE`。`hibi_runtime` にだけ CRUD を `GRANT`
- 公開 ID と `user_id` は UUID。日時は `timestamptz`
- 文字列は `text` + check。変更しやすい列挙は DB enum にしない
- RLS は現状なし。認可は FastAPI の所有者条件

## 一覧


| table | 用途 | 導入 |
| --- | --- | --- |
| `app.profiles` | Auth ユーザーに対する業務プロフィール | `20260924000100_foundation.sql` |
| `app.captures` | 生入力 1 件と、その処理状態、AI の判定結果 | `20260927090452_captures.sql` ほか |
| `app.capture_scenarios` | 判定から作った「やること」の提案と、ユーザーの進捗 | `20261104141318_capture_scenarios.sql` ほか |
| `app.capture_embeddings` | 検索用の embedding。本文から作り直せる派生データ | `20261107075656_capture_embeddings.sql` |
| `app.outbox_events` | Worker への処理依頼の配送待ち | `20261026000500_capture_outbox.sql` |


参照のみ（定義しない）: `auth.users`

## テーブルの責任

`app.captures` と `app.capture_scenarios` は 1 対 0..1 で、同じ Capture に付く。混ざりやすいので、持ち主と性質で分ける。

| | `app.captures` | `app.capture_scenarios` |
| --- | --- | --- |
| 持つもの | ユーザーが書いた 1 文と、システムがそれをどう理解したか | その文から作った「やること」の中身と、ユーザーがそれをどう扱ったか |
| 性質 | 事実と判定。完了後は変わらない | ユーザーの操作で変わる状態 |
| 存在 | 入力 1 件につき必ず 1 行 | route が `shopping`、`reminder`、`expense` で completed のときだけ 1 行 |
| 主キー | `id` | `capture_id`(`captures.id` を参照する 1 対 0..1) |
| 書く者 | API(作成、本文の更新、削除、retry)と Worker(処理の完了) | Worker(完了と同じ transaction で `proposed` を作る)と API(確認、完了) |
| 削除 | Capture の削除 | Capture を消すと `ON DELETE CASCADE` で消える。単独では消さない |

### 置き場所の決め方

列を足すときは、次の 2 つで決める。

1. **AI か policy が決めた判定の結果か。** そうなら `captures`。`category`、`route`、`urgency`、`urgency_score`、`confidence`、`clarification_text` と、各 version がこれに当たる。完了の更新で 1 回書いたら、以後は変えない。
2. **提案の中身か、ユーザーの進捗か。** そうなら `capture_scenarios`。`title`、`amount`、`remind_text`、`due_at`(提案の中身)、`status`、`done_at`(ユーザーの進捗)がこれに当たる。

`urgency_score` は `captures` で、`due_at` は `capture_scenarios` にある。前者は Jev の判定そのもの、後者は `remind_text` からシナリオの policy が求めた提案の一部だから。

### 分けている理由

- **一部の Capture にしか無い。** note と chat、聞き返し(clarify)にはシナリオが無い。`captures` に列を足すと、大半の行で null になり、check も複雑になる。
- **更新の経路が違う。** `captures` の処理状態は、`status` と `processing_generation` を条件にした UPDATE で守っている。ユーザーが `done_at` を書く操作と同じ行に置くと、Worker の条件付き UPDATE と競合する。
- **分類の整合性を保てる。** `captures` の分類列は、7 列がすべて null か、すべて非 null のどちらかという check で守っている。シナリオの列は、この check に入れない。

### 書き込みの境界

- Worker が書いてよいシナリオの `status` は `proposed` だけ。`accepted` は確認 API だけが書く。
- Worker は `done_at` を書かない。完了と取り消しは API だけが行う。
- Capture が completed でないシナリオは作らない。Worker は、完了の UPDATE と同じ transaction でシナリオを INSERT する。
- 読み取りは、Capture を主として `LEFT JOIN`(シナリオが無い Capture もある)で行う。Today だけは、シナリオを主にして `INNER JOIN` し、完了済みを除く。

## `app.profiles`

Auth ユーザー作成時に trigger `on_auth_user_created` が 1 行挿入する。API が直接ユーザーを作らない。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `user_id` | `uuid` | NO | — | PK。`auth.users(id)` への FK |
| `display_name` | `text` | YES | — | 表示名。`char_length <= 100` |
| `timezone` | `text` | NO | `'Asia/Tokyo'` | IANA 名。空文字禁止。既定は `20261114023753_today_priority.sql` で `'UTC'` から変更 |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |
| `updated_at` | `timestamptz` | NO | `now()` | 更新時刻 |

制約・付属物:

- PK: `user_id`
- FK: `user_id → auth.users(id)` `ON DELETE CASCADE`
- `ck_profiles__timezone_not_empty`
- trigger: `auth.users` INSERT 後に `app.create_auth_profile()`
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE

## `app.captures`

ユーザーが投入した生テキスト 1 件と、その処理状態、AI の判定結果。列の意味は [Capture 契約](./13-week3-capture-contract.md) に従う。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | — | PK。アプリが `uuid.uuid7()` で発行 |
| `user_id` | `uuid` | NO | — | 所有者。`app.profiles(user_id)` への FK |
| `raw_text` | `text` | NO | — | 生入力。trim 後 1〜2000 文字 |
| `status` | `text` | NO | `'pending'` | `pending` / `processing` / `completed` / `failed` |
| `idempotency_key` | `text` | NO | — | 作成冪等キー。8〜128 文字。API に出さない |
| `request_hash` | `text` | NO | — | 作成 payload の SHA-256 hex（64 桁）。API に出さない |
| `processing_generation` | `integer` | NO | `1` | 処理の世代。retry のたびに 1 増える。job の引数と照合する |
| `category` | `text` | YES | — | `shopping` / `reminder` / `expense` / `note` / `chat` |
| `route` | `text` | YES | — | category、または確信度が足りないときの `clarify` |
| `urgency` | `text` | YES | — | `low` / `normal` / `high`。現状の policy は `normal` 固定 |
| `urgency_score` | `numeric(3,2)` | YES | — | Jev の緊急度。0 以上 1 以下。範囲外のときと、導入前の行は null |
| `confidence` | `numeric` | YES | — | 分類の確信度。0 以上 1 以下 |
| `policy_version` | `text` | YES | — | route の policy の版 |
| `question_version` | `text` | YES | — | 分類の質問の版 |
| `processed_at` | `timestamptz` | YES | — | 分類を保存した時刻 |
| `clarification_text` | `text` | YES | — | 聞き返し文。`route = clarify` のときだけ。1〜500 文字 |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |
| `updated_at` | `timestamptz` | NO | `now()` | 更新時刻 |

制約・付属物:

- PK: `id`
- FK: `user_id → app.profiles(user_id)` `ON DELETE CASCADE`
- `uq_captures__user_id_idempotency_key`（`user_id`, `idempotency_key`）
- `ck_captures__raw_text_length`
- `ck_captures__status`
- `ck_captures__idempotency_key_length`
- `ck_captures__request_hash_sha256`
- `ck_captures__processing_generation`（1 以上）
- `ck_captures__category`、`ck_captures__route`、`ck_captures__urgency`、`ck_captures__confidence`
- `ck_captures__classification_presence`（`category`、`route`、`urgency`、`confidence`、`policy_version`、`question_version`、`processed_at` の 7 列は、すべて null かすべて非 null）
- `ck_captures__clarification_text`（null、または 1〜500 文字）
- `ck_captures__urgency_score`（null、または 0 以上 1 以下）。7 列の check には入れない
- index: `ix_captures__user_id_created_at`（`user_id`, `created_at DESC`, `id DESC`）
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE
- RLS: なし

状態の遷移は [Week 4 非同期 Capture](./22-week4-async-capture.md) に従う。分類の 7 列は、`processing` から `completed` へ進む 1 回の UPDATE で、同じ世代のときだけ書く。

## `app.capture_scenarios`

completed の Capture から作った「やること」の提案と、そのユーザーの進捗。[Week 7 日常シナリオ](./25-week7-daily-scenarios.md)と[Week 9 Today 優先度](./27-week9-today-priority.md)の契約に従う。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `capture_id` | `uuid` | NO | — | PK。`app.captures(id)` への FK。1 Capture につき 1 行まで |
| `user_id` | `uuid` | NO | — | 所有者。Capture と同じ値。`app.profiles(user_id)` への FK |
| `route` | `text` | NO | — | `shopping` / `reminder` / `expense` |
| `status` | `text` | NO | — | `proposed`(提案)/ `accepted`(ユーザーが確認) |
| `title` | `text` | NO | — | 画面に出す題。1〜200 文字 |
| `amount` | `integer` | YES | — | 円の整数。支出で金額が取れたときだけ。0 以上 |
| `remind_text` | `text` | YES | — | 予定の時刻表現。reminder で取り出せたときだけ。1〜200 文字 |
| `policy_version` | `text` | NO | — | シナリオの policy の版。`capture-scenario-v1` |
| `due_at` | `timestamptz` | YES | — | 期限。`remind_text` をユーザーの timezone で直した値。reminder で解釈できたときだけ |
| `done_at` | `timestamptz` | YES | — | ユーザーが完了にした時刻。未完了は null。取り消すと null に戻る |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |
| `updated_at` | `timestamptz` | NO | `now()` | 更新時刻 |

制約・付属物:

- PK: `capture_id`
- FK: `capture_id → app.captures(id)` `ON DELETE CASCADE`、`user_id → app.profiles(user_id)` `ON DELETE CASCADE`
- `ck_capture_scenarios__route`、`ck_capture_scenarios__status`、`ck_capture_scenarios__title`、`ck_capture_scenarios__amount`、`ck_capture_scenarios__remind_text`、`ck_capture_scenarios__policy_version`
- index: PK のみ。Today は所有者の未完了の行をすべて読むが、件数が小さい間は計測してから足す
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE

`status` の `accepted` は「ユーザーが提案を確認した」ことを表し、「やることを済ませた」ことは表さない。済ませたかどうかは `done_at` で表す。2 つは独立していて、`proposed` のまま `done_at` を書くことも、`accepted` で未完了のままにすることもできる。

## `app.capture_embeddings`

検索用の embedding。本文から作り直せる派生データで、検索 API が読むだけにする。[Week 8 検索](./26-week8-search.md)の契約に従う。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `capture_id` | `uuid` | NO | — | PK。`app.captures(id)` への FK。1 Capture につき 1 行まで |
| `user_id` | `uuid` | NO | — | 所有者。`app.profiles(user_id)` への FK |
| `content_text` | `text` | NO | — | embedding した本文。1〜2000 文字 |
| `content_hash` | `text` | NO | — | 本文の SHA-256 hex（64 桁）。同じなら作り直さない |
| `embedding` | `vector(8)` | NO | — | cosine 距離で比べるベクトル |
| `embedding_model` | `text` | NO | — | モデル名。fake は `capture-embed-fake-v1` |
| `embedding_dimensions` | `integer` | NO | — | 次元数。現状は 8 |
| `embedding_version` | `text` | NO | — | `capture-embed-v1` |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |
| `updated_at` | `timestamptz` | NO | `now()` | 更新時刻 |

制約・付属物:

- PK: `capture_id`
- FK: `capture_id → app.captures(id)` `ON DELETE CASCADE`、`user_id → app.profiles(user_id)` `ON DELETE CASCADE`
- `ck_capture_embeddings__content_text`、`ck_capture_embeddings__hash`、`ck_capture_embeddings__embedding_model`、`ck_capture_embeddings__embedding_dimensions`、`ck_capture_embeddings__embedding_version`
- index: `ix_capture_embeddings__user_id`（`user_id`）。HNSW は付けない
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE

## `app.outbox_events`

Capture の処理依頼を、arq へ配送するまでの待ち行列。Capture の作成と同じ transaction で書き、relay が配送後に `published` にする。[Week 4 非同期 Capture](./22-week4-async-capture.md) の契約に従う。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | — | PK |
| `user_id` | `uuid` | NO | — | 所有者。`app.profiles(user_id)` への FK |
| `aggregate_type` | `text` | NO | — | `capture` |
| `aggregate_id` | `uuid` | NO | — | 対象の Capture。`app.captures(id)` への FK |
| `event_type` | `text` | NO | — | `capture.processing_requested` |
| `processing_generation` | `integer` | NO | — | 依頼した処理の世代。1 以上 |
| `status` | `text` | NO | `'pending'` | `pending` / `published` |
| `available_at` | `timestamptz` | NO | `now()` | この時刻以降に配送してよい |
| `published_at` | `timestamptz` | YES | — | 配送した時刻 |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |

制約・付属物:

- PK: `id`
- FK: `user_id → app.profiles(user_id)` `ON DELETE CASCADE`、`aggregate_id → app.captures(id)` `ON DELETE CASCADE`
- `ck_outbox_events__aggregate_type`、`ck_outbox_events__event_type`、`ck_outbox_events__processing_generation`、`ck_outbox_events__status`
- index: `ix_outbox_events__pending_available`（`available_at`, `id`、`status = 'pending'` の行だけ）
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE

## 関連

- [ER図](./14-er.md)
- [Week 3 Capture 契約](./13-week3-capture-contract.md)
- [Week 7 日常シナリオ](./25-week7-daily-scenarios.md)
- [Week 8 検索](./26-week8-search.md)
- [Week 9 Today 優先度](./27-week9-today-priority.md)
- [プロジェクト構成](./02-project-structure.md)
