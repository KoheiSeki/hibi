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
| `app.captures` | 未整理の生入力 1 件 | `20260927090452_captures.sql` |


参照のみ（定義しない）: `auth.users`

## `app.profiles`

Auth ユーザー作成時に trigger `on_auth_user_created` が 1 行挿入する。API が直接ユーザーを作らない。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `user_id` | `uuid` | NO | — | PK。`auth.users(id)` への FK |
| `display_name` | `text` | YES | — | 表示名。`char_length <= 100` |
| `timezone` | `text` | NO | `'UTC'` | IANA 名。空文字禁止 |
| `created_at` | `timestamptz` | NO | `now()` | 作成時刻 |
| `updated_at` | `timestamptz` | NO | `now()` | 更新時刻 |

制約・付属物:

- PK: `user_id`
- FK: `user_id → auth.users(id)` `ON DELETE CASCADE`
- `ck_profiles__timezone_not_empty`
- trigger: `auth.users` INSERT 後に `app.create_auth_profile()`
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE

## `app.captures`

ユーザーが投入した生テキスト。Week 3 の API は `status = pending` のみ書く。列の意味は [Capture 契約](./13-week3-capture-contract.md) に従う。

| 列 | 型 | NULL | 既定 | 説明 |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | — | PK。アプリが `uuid.uuid7()` で発行 |
| `user_id` | `uuid` | NO | — | 所有者。`app.profiles(user_id)` への FK |
| `raw_text` | `text` | NO | — | 生入力。trim 後 1〜2000 文字 |
| `status` | `text` | NO | `'pending'` | `pending` / `processing` / `completed` / `failed` |
| `idempotency_key` | `text` | NO | — | 作成冪等キー。8〜128 文字。API に出さない |
| `request_hash` | `text` | NO | — | 作成 payload の SHA-256 hex（64 桁）。API に出さない |
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
- index: `ix_captures__user_id_created_at`（`user_id`, `created_at DESC`, `id DESC`）
- 権限: `anon` / `authenticated` は不可。`hibi_runtime` は SELECT/INSERT/UPDATE/DELETE
- RLS: なし

## 関連

- [ER図](./14-er.md)
- [Week 3 Capture 契約](./13-week3-capture-contract.md)
- [プロジェクト構成](./02-project-structure.md)
