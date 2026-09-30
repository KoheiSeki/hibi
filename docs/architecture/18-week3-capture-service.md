# Week 3 Step 5: Capture Service

[Capture 契約](./13-week3-capture-contract.md) の実装順 5。[Capture Repository](./17-week3-capture-repository.md) の上に、業務ルールだけを載せる。Router / OpenAPI / CORS / Web は次ステップ。

## このステップのゴール

`CaptureRepository` を呼び、trim・冪等・cursor・所有者 404 を型付き例外と戻り値にする。HTTP status と JSON はまだ組み立てない。

完了条件:

- `rawText` は trim してから長さ判定する。空・空白のみ・2,000 超は例外
- 作成は `uuid.uuid7()` と trim 後 SHA-256 hex を Service が決める
- 同じ `(user_id, idempotency_key)` かつ同じ hash は既存行を返す（insert しない）
- 同じ key・異なる hash は `IdempotencyKeyConflictError`
- `IntegrityError` は握りつぶさない。再読込して hash を比べる
- Repository の `None` / `False` は `CaptureNotFoundError`（他者も同じ）
- cursor の encode / decode は Service。不正は `MalformedCursorError`
- `HTTPException` を上げない。`session.commit()` もしない
- 通常 CI の unit test（Repository は fake）で上記を確認する

## やらないこと


| 先送り | 理由 |
| --- | --- |
| `router.py` / `schemas.py` | HTTP・Pydantic 境界・`Location` は次 |
| `create_app` mount / CORS / `problem_responses` / OpenAPI client | Router ステップ |
| `policies.py` | 状態遷移がまだ無い |
| `Principal` や FastAPI `Depends` | Service は `user_id: UUID` を command で受ける |
| `session.commit()` | [16](./16-week3-db-repository.md) のまま |
| 実 PostgreSQL の integration | Repository で済んでいる。このステップは fake |
| `CaptureResponse` への写し | API 境界型は Router |

## 依存の流れ

```text
CaptureService(repository)
  → trim / hash / uuid7 / cursor / 冪等判定
    → CaptureRepository（または fake）
      → domain Capture
    → command の戻り、または ApplicationError 配下
```

```text
HTTP はまだ来ない
Pydantic Request はまだ来ない
Service は status code を数字で返さない
Handler は既存の ApplicationError 変換のまま
```

## 作成・変更ファイル

### 新規


| ファイル | 要点 |
| --- | --- |
| `apps/api/src/hibi/modules/captures/errors.py` | `ApplicationError` 配下。HTTP を import しない |
| `apps/api/src/hibi/modules/captures/types.py` | domain `Capture` と Service 入出力。Pydantic にしない |
| `apps/api/src/hibi/modules/captures/service.py` | `CaptureService` だけ |
| `apps/api/tests/test_capture_service.py` | fake Repository。`-m 'not integration'` で走る |


### 変更

なしでよい。`repository.py` / `models.py` / `hibi/db` / `main.py` / `exception_handlers.py` は触らない。`errors[]` 付き 422 の handler 拡張は Router ステップ。

## 実装要点

### 例外

[04](./04-error-handling.md) どおり、業務失敗は型付き例外。`str(exception)` を契約にしない。既存 `handle_application_error` はクラス属性 `problem_type` / `title` / `status` / `detail` を読む。

置き場所は `modules/captures/errors.py`。[core/errors.py](../../apps/api/src/hibi/core/errors.py) に Capture 業務を足さない。


| クラス | status | `type` 末尾 | 固定 `detail` |
| --- | --- | --- | --- |
| `IdempotencyKeyRequiredError` | 400 | `idempotency-key-required` | `Idempotency-Key header is required.` |
| `IdempotencyKeyInvalidError` | 400 | `idempotency-key-invalid` | `Idempotency-Key is invalid.` |
| `MalformedCursorError` | 400 | `malformed-cursor` | `The pagination cursor is invalid.` |
| `IdempotencyKeyConflictError` | 409 | `idempotency-key-conflict` | `Idempotency-Key was reused with a different payload.` |
| `CaptureNotFoundError` | 404 | `capture-not-found` | `The requested capture does not exist.` |
| `CaptureTextInvalidError` | 422 | `validation-error` | `One or more fields are invalid.` |

`title` は [契約の表](./13-week3-capture-contract.md#エラー契約) に合わせる。`CaptureNotFoundError` は `capture_id` を持ってよい。メッセージには出さない。

401 は作らない。未認証は既存の `get_principal`（Router）。

### 内部型

API の `CreateCaptureRequest` はまだ作らない。Service 入力は command。

置き場所は `types.py`。`service.py` に混ぜない。domain `Capture` もここに置く。`CreateCaptureResult` / `CapturePage` が参照するので、`repository.py` に残すと `types` → `repository` の逆依存になる。Repository は `types` を import する。`Capture` を入力 command には使わない。`schemas.py` にも置かない（HTTP 境界は次ステップ）。

```text
CreateCaptureCommand
  user_id: UUID
  raw_text: str          # 未 trim。呼び出し側の原文
  idempotency_key: str | None

CreateCaptureResult
  capture: Capture
  created: bool          # True なら初回。Router が 201 / 200 に分ける

UpdateCaptureCommand
  user_id: UUID
  capture_id: UUID
  raw_text: str          # 未 trim

ListCapturesQuery
  user_id: UUID
  limit: int | None      # None なら 20
  cursor: str | None     # 不透明。無ければ先頭ページ

CapturePage
  items: list[Capture]
  next_cursor: str | None
  has_next_page: bool
```

`created: bool` は HTTP を知っているわけではない。「新規 insert したか」だけを表す。

### `CaptureService`

```text
def __init__(self, session: AsyncSession, repository: CaptureRepository) -> None
```

`Principal` は持たない。`commit()` はしない。`IntegrityError` のあとだけ `session.rollback()` する（下の作成フロー）。同じ session を Repository に渡す。

| method | 契約 |
| --- | --- |
| `create_capture(command)` | 下の作成フロー。戻りは `CreateCaptureResult` |
| `get_capture(user_id, capture_id)` | 無ければ `CaptureNotFoundError`。戻りは `Capture` |
| `list_captures(query)` | 既定 20、上限 50。`CapturePage` |
| `update_capture(command)` | trim して `update_capture`。無ければ `CaptureNotFoundError` |
| `delete_capture(user_id, capture_id)` | 無ければ / 他者は `CaptureNotFoundError`。成功は `None` |

禁止:

- `HTTPException`
- `session.commit()`
- body / command から `user_id` 以外の所有者を信じる
- `IntegrityError` を成功扱いで握りつぶす
- 未 trim の `raw_text` を hash する
- SQL 条件や `(created_at, id)` を cursor 文字列のまま返す
- log に `raw_text` / token / `request_hash` を出す

### 作成フロー

```text
1. idempotency_key が None / 空 → IdempotencyKeyRequiredError
2. 印字可能 ASCII（0x20-0x7E）かつ 8〜128 文字でなければ → IdempotencyKeyInvalidError
3. raw_text を strip
4. 長さ 0 または MAX_CAPTURE_LENGTH（2000）超 → CaptureTextInvalidError
5. request_hash = SHA-256(trim 後 UTF-8).hexdigest()（小文字 64 桁）
6. get_by_idempotency_key(user_id, key)
   - あり、hash 一致 → CreateCaptureResult(existing, created=False)
   - あり、hash 不一致 → IdempotencyKeyConflictError
7. なし → create_capture(id=uuid7(), raw_text=trim 済み, key, hash)
   - 成功 → CreateCaptureResult(new, created=True)
   - IntegrityError → 同じ session で次の SELECT はできない。`await session.rollback()` してから
     `get_by_idempotency_key` を再実行（他 request が commit 済みの行を読む）
       - あり、hash 一致 → created=False
       - あり、hash 不一致 → IdempotencyKeyConflictError
       - なし → IntegrityError を再 raise（消して成功にしない）
```

`status` は渡さない。Repository が `'pending'` にする。

### 一覧と cursor

Repository は復号済みの `(created_at, id)` だけを知る。不透明文字列は Service。

```text
limit = 20 if query.limit is None else query.limit
1 ≤ limit ≤ 50 を満たす。範囲外は 50 へ clamp（専用 error は作らない。Query 検証は Router）
cursor があれば decode。失敗 → MalformedCursorError
list_for_user(..., limit=limit+1, created_at=..., id=...)
limit 件を返す。+1 件目があれば has_next_page=True
next_cursor は返した最後の行の (created_at, id) を encode
```

encode は SQL を露出さない。契約例と同じ形でよい。

```text
{"c": "<createdAt RFC 3339 UTC>", "i": "<uuid>"}
```

これを URL-safe Base64（padding なし）にする。`c` / `i` 欠落、UUID 不正、時刻不正はすべて `MalformedCursorError`。

時刻は UTC。`+09:00` へ変換しない。

### 更新・削除

`update_capture` も作成と同じ trim / 長さ判定。`id` / `status` / hash は変えない。Repository が `updated_at` を書く。

`delete_capture` は Repository が `False` なら `CaptureNotFoundError`。再削除も同じ例外（Router が 404）。

## テスト方針（このステップ）

`test_capture_service.py` は通常 CI に入れる。fake はメモリ上の dict。SQLAlchemy も `get_session` も使わない。

確認する振る舞い:

1. 作成すると `created is True`、`status == "pending"`、`raw_text` は trim 済み
2. 同じ key・同じ本文の再作成は `created is False`、同じ `id`。fake の行数は 1
3. 同じ key・異なる本文は `IdempotencyKeyConflictError`
4. key なし / 短すぎは required または invalid
5. 空白のみ・2001 文字は `CaptureTextInvalidError`
6. 無い ID / 他者 ID の get・update・delete は `CaptureNotFoundError`
7. 一覧に他者行が混ざらない。新しい順
8. 不正 cursor は `MalformedCursorError`
9. fake が `IntegrityError` を上げたあと、hash 一致なら replay、不一致なら conflict

401 / `Location` / OpenAPI / CORS は書かない。既存の `test_capture_repository.py` は壊さない。

## 実装順

1. failing unit を先に書く（`CaptureService` が無いところで落ちる）
2. `errors.py`
3. command と `CaptureService` を通す
4. `uv run --project apps/api pytest apps/api/tests/test_capture_service.py -v`

## 次ステップ（Router / OpenAPI）

`CreateCaptureRequest` / `CaptureResponse`、`get_principal`、`Location`、`data` エンベロープ、`problem_responses`、CORS の `Idempotency-Key`、`pnpm openapi:client`。Service の例外はそのまま Global Exception Handler に載せる。決定的な HTTP 契約テスト（TestClient）はそちら。

## 関連

- [Capture 契約](./13-week3-capture-contract.md)
- [Capture Repository](./17-week3-capture-repository.md)
- [エラーハンドリング](./04-error-handling.md)
- [プロジェクト構成](./02-project-structure.md)
- [命名規約](./03-naming-conventions.md)
- [API・データ契約](./06-api-data-contracts.md)
