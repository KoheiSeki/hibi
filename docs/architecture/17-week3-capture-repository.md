# Week 3 Step 4: Capture Repository

[Capture 契約](./13-week3-capture-contract.md) の実装順 4。[DB 接続基盤](./16-week3-db-repository.md) の上に、所有者条件付きの永続化だけを載せる。Service / Router / OpenAPI / Web は次ステップ。

## このステップのゴール

`get_session` から渡した `AsyncSession` で、`app.captures` の作成・取得・一覧・更新・削除ができる。HTTP status と冪等の意味判断はまだしない。

完了条件:

- `CaptureModel` が [テーブル定義](./15-table-catalog.md) の列と一致する
- `create_all` も Alembic もしない。schema の正は migration のまま
- Repository のすべての query に `user_id` が入る
- 他者の ID では行が取れない（`None` / `False`）。404 は上げない
- `commit()` は Repository が呼ばない（`get_session` のまま）
- `@pytest.mark.integration` で所有者分離と unique 競合を実 PostgreSQL で確認する

## やらないこと


| 先送り | 理由 |
| --- | --- |
| `router.py` / `schemas.py` / `service.py` / `errors.py` | HTTP と冪等判定は Service / Router |
| `policies.py` | 状態遷移がまだ無い |
| `db/crud/` や汎用 Repository | [プロジェクト構成](./02-project-structure.md) に反する |
| `trim` / SHA-256 / cursor の encode | Service の責務 |
| `Principal` や FastAPI `Depends` | Repository は `user_id: UUID` を引数で受ける |
| Profile の SQLAlchemy model | Capture は `user_id` だけで足りる |


## 依存の流れ

```text
get_session
  → CaptureRepository(session)
    → CaptureModel（schema=app）
      → PostgreSQL app.captures
    → domain Capture を返す
```

```text
HTTP はまだ来ない
Service はまだ無い
Repository は SQL と行の有無だけを知る
```

## 作成・変更ファイル

### 新規


| ファイル | 要点 |
| --- | --- |
| `apps/api/src/hibi/modules/captures/__init__.py` | 空、または `CaptureRepository` を公開 |
| `apps/api/src/hibi/modules/captures/models.py` | `CaptureModel`。`Base` を継承。`__table_args__ = {"schema": "app"}` |
| `apps/api/src/hibi/modules/captures/repository.py` | `CaptureRepository`。domain `Capture` は Service 以降 `types.py` |
| `apps/api/tests/integration/test_capture_repository.py` | 実 Postgres。通常 CI からは除外 |


### 変更

なしでよい。`hibi/db` と `main.py` は触らない。migration も触らない。

## 実装要点

### `CaptureModel`

[テーブル定義](./15-table-catalog.md) の写し。check / unique / index は model に二重定義しない。

```text
__tablename__ = "captures"
schema = "app"

id: UUID
user_id: UUID
raw_text: str
status: str
idempotency_key: str
request_hash: str
created_at: datetime
updated_at: datetime
```

- `id` の DB default は置かない。呼び出し側が `uuid.uuid7()` を渡す
- SQLAlchemy 行を Router の response に使わない

### domain `Capture`

Repository の戻り。Service に SQLAlchemy を漏らさない。

```text
Capture
  id: UUID
  user_id: UUID
  raw_text: str
  status: str
  idempotency_key: str
  request_hash: str
  created_at: datetime
  updated_at: datetime
```

`idempotency_key` / `request_hash` は API に出さないが、次の Service が 200 / 409 を決めるので domain には載せる。

`models.py` に dataclass を混ぜない。Service 導入後の置き場は `types.py`（[18](./18-week3-capture-service.md)）。

### `CaptureRepository`

```text
def __init__(self, session: AsyncSession) -> None
```

HTTP も Principal も知らない。`user_id` は毎回引数。session のユーザーに依存しない。

| method | 契約 |
| --- | --- |
| `get_by_id(user_id, capture_id)` | 無ければ `None`。`user_id` 不一致も `None` |
| `get_by_idempotency_key(user_id, key)` | 無ければ `None` |
| `list_for_user(user_id, *, limit, created_at=None, id=None)` | `created_at DESC, id DESC`。cursor は **復号済み** の境界。不透明文字列は扱わない |
| `create_capture(...)` | insert のみ。`id` / `raw_text` / `idempotency_key` / `request_hash` は呼び出し側が渡す。trim も hash もしない。`status` は `'pending'` |
| `update_capture(user_id, capture_id, raw_text)` | 所有者行だけ。`raw_text` と `updated_at` のみ。無ければ `None` |
| `delete_capture(user_id, capture_id)` | 所有者行だけ。無ければ `False`、削除したら `True` |

`create_capture` の引数（推奨）:

```text
id: UUID
user_id: UUID
raw_text: str
idempotency_key: str
request_hash: str
```

禁止:

- `save_`
- `user_id` なしの `get_by_id(capture_id)`
- 他者行を例外にする
- `IntegrityError` を握りつぶして成功扱いする
- `session.commit()`

同じ `(user_id, idempotency_key)` の同時 insert は `IntegrityError` のまま上げる。Service が再読込して hash を比べる。

### 一覧の cursor

Repository は「この `(created_at, id)` より古い行」だけを知る。

```text
WHERE user_id = :user_id
  AND (created_at, id) < (:created_at, :id)   -- 境界があるとき
ORDER BY created_at DESC, id DESC
LIMIT :limit
```

`limit` の default / 上限（20 / 50）は Service。Repository は渡された `limit` を使う。

### テストデータの前提

`user_id` は `app.profiles` への FK。integration では `auth.users` に UUID を insert する。foundation の trigger が `app.profiles` を作る。Profile を手で insert しなくてよい。

## テスト方針（このステップ）

通常 CI は `-m 'not integration'` のまま。接続不能なら [16](./16-week3-db-repository.md) と同じく skip。

`test_capture_repository.py` で確認する振る舞い:

1. 所有者 A で `create_capture` した行を、A の `get_by_id` で取れる
2. 同じ `id` を他者 B の `user_id` で `get_by_id` すると `None`
3. `get_by_idempotency_key` が A では当たり、B では `None`
4. `list_for_user(A)` に B の行が混ざらない。新しい順
5. `update_capture` は所有者だけ本文が変わり、他者は `None` のまま
6. `delete_capture` は所有者だけ `True`。その後 A の `get_by_id` は `None`
7. 同じ `(user_id, idempotency_key)` の二度目の `create_capture` は `IntegrityError`

決定的な HTTP 契約（201 / 409 / 404）は、Repository fake で次の Service / Router ステップに書く。

既存の `test_db_session.py` は残す。このステップでは壊さない。

## 実装順

1. failing integration を先に書く（`CaptureRepository` が無いところで落ちる）
2. `CaptureModel` を最小で足す
3. `Capture` と `CaptureRepository` を通す
4. `uv run --project apps/api pytest apps/api/tests/integration/test_capture_repository.py -m integration -v`

## 次ステップ（Service）

方針は [18-week3-capture-service.md](./18-week3-capture-service.md)。

## 関連

- [Capture 契約](./13-week3-capture-contract.md)
- [DB 接続基盤](./16-week3-db-repository.md)
- [テーブル定義](./15-table-catalog.md)
- [プロジェクト構成](./02-project-structure.md)
- [命名規約](./03-naming-conventions.md)
