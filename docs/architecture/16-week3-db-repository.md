# Week 3 Step 3: DB接続基盤

[Capture 契約](./13-week3-capture-contract.md) の実装順 3 のうち、**接続基盤だけ**をこのステップにする。Capture の model / Repository CRUD / Service / Router は次ステップ。

## このステップのゴール

FastAPI が `HIBI_DATABASE_URL`（`hibi_runtime_user`）で PostgreSQL に届き、request 境界の session を渡せる。

完了条件:

- `sqlalchemy[asyncio]` が入っている
- `HIBI_DATABASE_URL` から async engine / session が作れる
- 成功時 commit、例外時 rollback を session dependency が行う
- shutdown で engine を dispose する
- `create_all` も Alembic もしない。schema の正は `supabase/migrations` のまま
- 既存の `/health` / `/me` は DB 未設定でも動く
- integration で `SELECT 1`（または同等の接続確認）ができる。繋がらなければ skip

## やらないこと


| 先送り | 理由 |
| --- | --- |
| `CaptureModel` / `CaptureRepository` | CRUD は次ステップ |
| `router.py` / `schemas.py` / `service.py` / `errors.py` | HTTP と業務ルールはさらに後 |
| Capture 行の insert / update / delete | このステップの検証対象外 |
| `/health/ready` の DB ping | Week 11 |
| 起動時 migration | [09-operations.md](./09-operations.md) |
| service role / Data API | 業務接続は runtime role のみ |


## 依存の流れ

```text
Settings.database_url
  → hibi.db.engine（AsyncEngine）
    → hibi.db.session（AsyncSession / get_session）
```

次ステップで `get_session` の先に `CaptureRepository` が乗る。

## 作成・変更ファイル

### 新規


| ファイル | 要点 |
| --- | --- |
| `apps/api/src/hibi/db/__init__.py` | `get_engine` / `get_session` の薄い入口 |
| `apps/api/src/hibi/db/base.py` | SQLAlchemy 2.0 `DeclarativeBase` のみ（次の model 用） |
| `apps/api/src/hibi/db/engine.py` | `create_async_engine`。process 内で engine は 1 つ |
| `apps/api/src/hibi/db/session.py` | `async_sessionmaker` と `get_session` |
| `apps/api/tests/integration/test_db_session.py` | 接続確認。通常 CI からは除外 |


### 変更


| ファイル | 要点 |
| --- | --- |
| `apps/api/pyproject.toml` | `sqlalchemy[asyncio]` を version 固定。`uv lock` |
| `apps/api/src/hibi/core/config.py` | `database_url: str`（`HIBI_DATABASE_URL`） |
| `apps/api/src/hibi/api/main.py` | lifespan で shutdown 時 `engine.dispose()` |
| `apps/api/.env.example` | 既存 URL を使う。変更しなくてよい |


`modules/captures/` 配下は作らない。

## 実装要点

- URL 形: `postgresql+asyncpg://hibi_runtime_user:...@127.0.0.1:54322/postgres`
- 接続ユーザーは `hibi_runtime_user`
- pool は小さめ（local 2〜5）
- `get_session` は commit / rollback する。呼び出し側は `commit()` しない
- `database_url` が無い通常起動では、DB を使わない endpoint を壊さない。engine は最初の利用時か lifespan 開始時に作る
- exception handler は rollback しない（[04-error-handling.md](./04-error-handling.md)）

```text
get_session
  async with Session() as session:
    try:
      yield session
      await session.commit()
    except:
      await session.rollback()
      raise
```

## テスト方針（このステップ）

通常 CI は `-m 'not integration'` のまま。

`test_db_session.py`:

1. URL 未設定または接続不能なら skip
2. session で `SELECT 1` が返る
3. runtime role で `app.captures` を `SELECT` できる（行の作成はしない）

## 次ステップ（Capture Repository）

接続が通ったあとで、`modules/captures/models.py` と `repository.py` を足す。`hibi/db` や `db/crud/` には置かない。公開 method は `get_by_id` / `get_by_idempotency_key` / `list_for_user` / `create_capture` / `update_capture` / `delete_capture`。すべての query に `user_id` を含め、他者は `None` にする。HTTP の CRUD はさらにその次の Service / Router である。

## 関連

- [Capture 契約](./13-week3-capture-contract.md)
- [テーブル定義](./15-table-catalog.md)
- [プロジェクト構成](./02-project-structure.md)
- [エラーハンドリング](./04-error-handling.md)
