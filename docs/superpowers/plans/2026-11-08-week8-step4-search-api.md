# Week 8 実装順 4: 検索 API を所有者条件つきで追加する 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/v1/captures/search` が、検証済みの `user_id` の `completed` な Capture だけを、キーワード検索か意味検索で近い順に最大 20 件返す。OpenAPI と TypeScript client を同じ変更で再生成する。

**Architecture:** 順位付けは [`search.py`](../../../apps/api/src/hibi/modules/captures/search.py) の `rank_capture_by_keyword` / `rank_captures_by_semantic` が既に持っている（実装順 1 でテスト済み）。この計画はその前後を繋ぐだけ: repository が所有者の `completed` 行を `SearchDocument` として読み出し、service が既存の ranker で並べて上位 20 件に切り、repository が その id 群の `Capture` を scenario 付きで返し、router が既存の `CaptureResponse` で返す。embedding は検索時に作り直さず、`capture_embeddings` の行をそのまま読む。

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2 (asyncio) / pgvector / pytest + pytest-asyncio / ruff / ty / @hey-api/openapi-ts

**参照仕様:** [docs/architecture/26-week8-search.md](../../architecture/26-week8-search.md)（「契約」「Port」「障害」「テスト」「実装順 4」）

**前提:** 実装順 1〜3 が完了していること（`bee285b` まで）。

## Global Constraints

- Python は `>=3.14,<3.15`。ruff は `line-length = 100`、lint は `E, F, I, UP, B, ASYNC, RUF`。整形は `ruff format`。
- pytest の既定は `-m 'not integration'`、`asyncio_mode = "auto"`。通常の pytest は Jev、LLM、embedding API を呼ばない。
- path は `GET /captures/search` で、`/{capture_id}` **より前に登録する**。後ろに置くと `search` が `capture_id` として UUID パースされ 422 になる。
- `q` は 1 文字以上 200 文字以下。`mode` は `keyword` か `semantic`。未指定は `keyword`。不正は 422 で、retry しない。
- 成功は 200。要素は既存の Capture 一覧と同じ `CaptureResponse`（`scenario` も載せてよい）。近い順に**最大 20 件**。
- 0 件は空配列で返す。404 にはしない。
- `pending`、`processing`、`failed` は検索対象にしない。別ユーザーの行はどちらの検索にも出さない。
- 意味検索は同じ `user_id` かつ同じ `embedding_version` の行だけを cosine で並べる。距離は cosine 固定。HNSW index は付けない。
- リクエストのたびに Capture 本文の embedding を作り直さない（クエリ文のベクトル化は 1 回だけ）。
- OpenAPI と client は同じ変更で再生成する（`just openapi`）。
- 画面（実装順 5）、Today の優先度（Week 9）、要約（Week 10）はこの計画に含めない。

## File Structure

| ファイル | 役割 | 変更 |
| --- | --- | --- |
| `apps/api/src/hibi/modules/captures/types.py` | 検索のクエリ型と定数 | `SearchCapturesQuery`、`CaptureSearchMode`、`CAPTURE_SEARCH_MODE_*`、`CAPTURE_SEARCH_LIMIT` を追加 |
| `apps/api/src/hibi/modules/captures/search.py` | 順位付け（純関数） | 変更なし |
| `apps/api/src/hibi/modules/captures/repository.py` | 所有者の `completed` 行の読み出し | `list_search_documents`、`list_captures_by_ids`、`_to_embedding` を追加 |
| `apps/api/src/hibi/modules/captures/service.py` | mode の振り分けと 20 件への切り詰め | `search_captures` を追加 |
| `apps/api/src/hibi/modules/captures/router.py` | endpoint | `GET /search` を `/{capture_id}` の前に追加 |
| `apps/api/src/hibi/modules/captures/schemas.py` | レスポンス | 変更なし（`CaptureResponse` を再利用） |
| `contracts/openapi.json` | 契約の正本 | 再生成 |
| `packages/api-client` | TypeScript client | 再生成 |

---

### Task 1: 検索のクエリ型と service を足す

DB も network も使わない。repository は fake に差し替え、順位付けは既存の `search.py` に任せる。

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/types.py`
- Modify: `apps/api/src/hibi/modules/captures/service.py`
- Test: `apps/api/tests/test_capture_search_service.py`（新規）

**Interfaces:**

- Consumes:
  - `hibi.modules.captures.search.SearchDocument(capture_id, user_id, status, text, embedding=None)`
  - `hibi.modules.captures.search.rank_capture_by_keyword(documents, *, user_id, query) -> list[UUID]`
  - `hibi.modules.captures.search.rank_captures_by_semantic(documents, *, user_id, query, embedder) -> list[UUID]`（async）
  - `hibi.ai.fake_embedder.FakeTextEmbedder`
- Produces:
  - `hibi.modules.captures.types.CAPTURE_SEARCH_MODE_KEYWORD = "keyword"`
  - `hibi.modules.captures.types.CAPTURE_SEARCH_MODE_SEMANTIC = "semantic"`
  - `hibi.modules.captures.types.CAPTURE_SEARCH_LIMIT = 20`
  - `hibi.modules.captures.types.CaptureSearchMode = Literal["keyword", "semantic"]`
  - `hibi.modules.captures.types.SearchCapturesQuery(user_id: UUID, q: str, mode: str)`
  - `CaptureService.search_captures(query: SearchCapturesQuery) -> list[Capture]`
  - repository に要求する 2 メソッド（Task 2 で実装）:
    - `list_search_documents(user_id: UUID) -> list[SearchDocument]`
    - `list_captures_by_ids(user_id: UUID, *, capture_ids: Sequence[UUID]) -> list[Capture]`

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/test_capture_search_service.py` を新規作成する。

```python
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_embedder import FakeTextEmbedder
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.search import SearchDocument
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    CAPTURE_SEARCH_MODE_KEYWORD,
    CAPTURE_SEARCH_MODE_SEMANTIC,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_PENDING,
    Capture,
    SearchCapturesQuery,
)

_OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
_OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
_NOW = datetime(2026, 10, 18, 14, 2, tzinfo=UTC)


def _capture(capture_id: UUID, raw_text: str, *, user_id: UUID = _OWNER_ID) -> Capture:
    return Capture(
        id=capture_id,
        user_id=user_id,
        raw_text=raw_text,
        status=CAPTURE_STATUS_COMPLETED,
        idempotency_key=str(capture_id),
        request_hash="a" * 64,
        processing_generation=1,
        category="shopping",
        route="shopping",
        urgency="normal",
        confidence=None,
        policy_version=None,
        question_version=None,
        processed_at=_NOW,
        clarification_text=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class FakeSearchRepository:
    def __init__(self, captures: list[Capture], *, statuses: dict[UUID, str] | None = None) -> None:
        self.captures = captures
        self.statuses = statuses or {}
        self.document_calls = 0

    async def list_search_documents(self, user_id: UUID) -> list[SearchDocument]:
        self.document_calls += 1
        documents: list[SearchDocument] = []
        for capture in self.captures:
            status = self.statuses.get(capture.id, capture.status)
            if capture.user_id != user_id or status != CAPTURE_STATUS_COMPLETED:
                continue
            documents.append(
                SearchDocument(
                    capture_id=capture.id,
                    user_id=capture.user_id,
                    status=status,
                    text=capture.raw_text,
                    embedding=await FakeTextEmbedder().embed_text(capture.raw_text),
                )
            )
        return documents

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        wanted = set(capture_ids)
        return [
            capture
            for capture in self.captures
            if capture.id in wanted and capture.user_id == user_id
        ]


def _service(repository: FakeSearchRepository) -> CaptureService:
    return CaptureService(
        cast(AsyncSession, None),
        cast(CaptureRepository, repository),
        FakeCaptureClassifier(),
        FakeClarificationGenerator(),
        FakeTextEmbedder(),
    )


def _query(q: str, *, mode: str = CAPTURE_SEARCH_MODE_KEYWORD) -> SearchCapturesQuery:
    return SearchCapturesQuery(user_id=_OWNER_ID, q=q, mode=mode)


_MILK_ID = UUID(int=1)
_ARTICLE_ID = UUID(int=2)
_LUNCH_ID = UUID(int=3)


def _default_captures() -> list[Capture]:
    return [
        _capture(_MILK_ID, "牛乳を買う"),
        _capture(_ARTICLE_ID, "あとで読む記事"),
        _capture(_LUNCH_ID, "ランチ 1200 円"),
    ]


@pytest.mark.asyncio
async def test_keyword_search_finds_the_matching_capture() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("牛乳"))

    assert [capture.id for capture in found] == [_MILK_ID]


@pytest.mark.asyncio
async def test_keyword_search_does_not_match_a_synonym() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("ミルク"))

    assert found == []


@pytest.mark.asyncio
async def test_keyword_search_finds_the_note() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(_query("記事"))

    assert [capture.id for capture in found] == [_ARTICLE_ID]


@pytest.mark.asyncio
async def test_semantic_search_finds_the_synonym() -> None:
    repository = FakeSearchRepository(_default_captures())

    found = await _service(repository).search_captures(
        _query("ミルク", mode=CAPTURE_SEARCH_MODE_SEMANTIC)
    )

    assert [capture.id for capture in found] == [_MILK_ID]


@pytest.mark.asyncio
async def test_semantic_search_does_not_return_milk_for_a_lunch_query() -> None:
    repository = FakeSearchRepository(_default_captures())

    # 固定ベクトルの本文で引く。単独の「ランチ」はhashで牛乳と同じ次元に落ちる
    found = await _service(repository).search_captures(
        _query("ランチ 1200 円", mode=CAPTURE_SEARCH_MODE_SEMANTIC)
    )

    assert [capture.id for capture in found] == [_LUNCH_ID]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [CAPTURE_SEARCH_MODE_KEYWORD, CAPTURE_SEARCH_MODE_SEMANTIC],
)
async def test_search_skips_unfinished_captures(mode: str) -> None:
    repository = FakeSearchRepository(
        _default_captures(), statuses={_MILK_ID: CAPTURE_STATUS_PENDING}
    )

    found = await _service(repository).search_captures(
        _query("牛乳" if mode == CAPTURE_SEARCH_MODE_KEYWORD else "ミルク", mode=mode)
    )

    assert found == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [CAPTURE_SEARCH_MODE_KEYWORD, CAPTURE_SEARCH_MODE_SEMANTIC],
)
async def test_search_skips_other_owners(mode: str) -> None:
    repository = FakeSearchRepository([_capture(_MILK_ID, "牛乳を買う", user_id=_OTHER_ID)])

    found = await _service(repository).search_captures(
        _query("牛乳" if mode == CAPTURE_SEARCH_MODE_KEYWORD else "ミルク", mode=mode)
    )

    assert found == []


@pytest.mark.asyncio
async def test_search_returns_at_most_twenty_captures() -> None:
    captures = [_capture(UUID(int=index + 10), "牛乳を買う") for index in range(25)]
    repository = FakeSearchRepository(captures)

    found = await _service(repository).search_captures(_query("牛乳"))

    assert len(found) == 20


@pytest.mark.asyncio
async def test_search_returns_an_empty_list_without_candidates() -> None:
    repository = FakeSearchRepository([])

    found = await _service(repository).search_captures(_query("牛乳"))

    assert found == []
    assert repository.document_calls == 1
```

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_search_service.py -v`
Expected: collection error（`ImportError: cannot import name 'CAPTURE_SEARCH_MODE_KEYWORD' from 'hibi.modules.captures.types'`）

- [x] **Step 3: types に検索の型と定数を足す**

`apps/api/src/hibi/modules/captures/types.py` の先頭 import を次にする。

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
```

`CAPTURE_PROCESSING_MAX_ATTEMPTS = 3` の下に定数を足す。

```python
CAPTURE_SEARCH_MODE_KEYWORD = "keyword"
CAPTURE_SEARCH_MODE_SEMANTIC = "semantic"
CAPTURE_SEARCH_LIMIT = 20

CaptureSearchMode = Literal["keyword", "semantic"]
```

`ListCapturesQuery` の下に query 型を足す。

```python
@dataclass(frozen=True, slots=True)
class SearchCapturesQuery:
    """Capture検索の入力。

    Attributes:
        user_id: 検証済みの所有者。検索はこのユーザーの行だけを対象にする。
        q: 検索語。router が1〜200文字で検証済み。
        mode: CAPTURE_SEARCH_MODE_KEYWORD か CAPTURE_SEARCH_MODE_SEMANTIC。
    """

    user_id: UUID
    q: str
    mode: str
```

- [x] **Step 4: service に search_captures を足す**

`apps/api/src/hibi/modules/captures/service.py` の import に足す。位置は isort の辞書順（`policies` の下、`repository` の上が `search`）。

```python
from hibi.modules.captures.search import (
    rank_capture_by_keyword,
    rank_captures_by_semantic,
)
```

`hibi.modules.captures.types` の import に `CAPTURE_SEARCH_LIMIT`、`CAPTURE_SEARCH_MODE_SEMANTIC`、`SearchCapturesQuery` を足す（既存のブロックにアルファベット順で差し込む）。

`list_captures` の下、`update_capture` の上に足す。

```python
    async def search_captures(self, query: SearchCapturesQuery) -> list[Capture]:
        """所有者の完了済みCaptureを、近い順に最大 CAPTURE_SEARCH_LIMIT 件返す。

        順位付けは search.py に任せる。mode が semantic ならクエリ文だけを
        embedder でベクトル化し、保存済みの embedding と比べる。本文の
        embedding は作り直さない。それ以外は TF-IDF のキーワード検索。
        0件なら空リストを返し、例外にはしない。

        Args:
            query: 所有者、検索語、検索方式。

        Returns:
            順位の高い順の Capture。scenario も含む。
        """
        documents = await self._repository.list_search_documents(query.user_id)

        if query.mode == CAPTURE_SEARCH_MODE_SEMANTIC:
            ranked = await rank_captures_by_semantic(
                documents, user_id=query.user_id, query=query.q, embedder=self._embedder
            )
        else:
            ranked = rank_capture_by_keyword(documents, user_id=query.user_id, query=query.q)

        capture_ids = ranked[:CAPTURE_SEARCH_LIMIT]
        if not capture_ids:
            return []

        captures = await self._repository.list_captures_by_ids(
            query.user_id, capture_ids=capture_ids
        )
        by_id = {capture.id: capture for capture in captures}
        # rankerの順位を正本にする。SQLのINは順序を保証しない
        return [by_id[capture_id] for capture_id in capture_ids if capture_id in by_id]
```

- [x] **Step 5: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_search_service.py -v`
Expected: 全 PASS

- [x] **Step 6: 整形と lint を通す**

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
```

Expected: `ruff` は PASS。`ty check` は `list_search_documents` と `list_captures_by_ids` が `CaptureRepository` に無いので `unresolved-attribute` **が 2 件出る**。Task 2 で消える。

- [x] **Step 7: Commit**

```bash
git add apps/api/src/hibi/modules/captures/types.py apps/api/src/hibi/modules/captures/service.py apps/api/tests/test_capture_search_service.py
git commit -m "feat(captures): rank owner captures for keyword and semantic search"
```

---

### Task 2: repository に検索用の読み出しを足す

所有者の `completed` 行を embedding 付きで読み出し、id 群から Capture を scenario 付きで返す。SQL を触るので integration テストを足す。

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/repository.py`
- Test: `apps/api/tests/integration/test_capture_repository.py`（末尾に追記）

**Interfaces:**

- Consumes: `CaptureModel`、`CaptureEmbeddingModel`、`CaptureScenarioModel`、`hibi.modules.captures.search.SearchDocument`、`hibi.ai.embedding.Embedding`、`_to_capture`
- Produces:
  - `CaptureRepository.list_search_documents(user_id: UUID) -> list[SearchDocument]`
  - `CaptureRepository.list_captures_by_ids(user_id: UUID, *, capture_ids: Sequence[UUID]) -> list[Capture]`

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/integration/test_capture_repository.py` の末尾に足す。既存の `session` fixture、`_insert_auth_user`、`_create_capture` ヘルパーをそのまま使う。

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_search_documents_returns_only_completed_rows_of_the_owner(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repository = CaptureRepository(session=session)

    completed = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    pending = await _create_capture(repository, owner_id, raw_text="あとで読む記事")
    other = await _create_capture(repository, other_id, raw_text="牛乳を買う")
    for capture_id in (completed.id, other.id):
        await session.execute(
            update(CaptureModel)
            .where(CaptureModel.id == capture_id)
            .values(status=CAPTURE_STATUS_COMPLETED)
        )
    session.add(
        CaptureEmbeddingModel(
            capture_id=completed.id,
            user_id=owner_id,
            content_text="牛乳を買う",
            content_hash=hashlib.sha256("牛乳を買う".encode()).hexdigest(),
            embedding=[1.0] + [0.0] * (CAPTURE_EMBED_DIMENSIONS - 1),
            embedding_model=CAPTURE_EMBED_FAKE_MODEL,
            embedding_dimensions=CAPTURE_EMBED_DIMENSIONS,
            embedding_version=CAPTURE_EMBED_VERSION,
        )
    )
    await session.flush()

    documents = await repository.list_search_documents(owner_id)

    assert [document.capture_id for document in documents] == [completed.id]
    assert pending.id not in {document.capture_id for document in documents}
    assert other.id not in {document.capture_id for document in documents}
    assert documents[0].text == "牛乳を買う"
    assert documents[0].embedding is not None
    assert documents[0].embedding.vector[0] == 1.0
    assert documents[0].embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert documents[0].embedding.version == CAPTURE_EMBED_VERSION


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_search_documents_keeps_rows_without_an_embedding(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    await _insert_auth_user(session, owner_id)
    repository = CaptureRepository(session=session)

    capture = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    await session.execute(
        update(CaptureModel)
        .where(CaptureModel.id == capture.id)
        .values(status=CAPTURE_STATUS_COMPLETED)
    )
    await session.flush()

    documents = await repository.list_search_documents(owner_id)

    assert [document.capture_id for document in documents] == [capture.id]
    assert documents[0].embedding is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_captures_by_ids_loads_the_scenario_for_the_owner(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    other_id = uuid4()
    await _insert_auth_user(session, owner_id)
    await _insert_auth_user(session, other_id)
    repository = CaptureRepository(session=session)

    first = await _create_capture(repository, owner_id, raw_text="牛乳を買う")
    second = await _create_capture(repository, owner_id, raw_text="ランチ 1200 円")
    other = await _create_capture(repository, other_id, raw_text="牛乳を買う")
    session.add(
        CaptureScenarioModel(
            capture_id=first.id,
            user_id=owner_id,
            route="shopping",
            status=CAPTURE_SCENARIO_STATUS_PROPOSED,
            title="牛乳",
            amount=None,
            remind_text=None,
            policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
        )
    )
    await session.flush()

    captures = await repository.list_captures_by_ids(
        owner_id, capture_ids=[second.id, first.id, other.id]
    )

    by_id = {capture.id: capture for capture in captures}
    assert set(by_id) == {first.id, second.id}
    assert by_id[first.id].scenario is not None
    assert by_id[first.id].scenario.title == "牛乳"
    assert by_id[second.id].scenario is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_captures_by_ids_returns_an_empty_list_without_ids(
    session: AsyncSession,
) -> None:
    owner_id = uuid4()
    await _insert_auth_user(session, owner_id)
    repository = CaptureRepository(session=session)

    assert await repository.list_captures_by_ids(owner_id, capture_ids=[]) == []
```

- [x] **Step 2: テストが落ちることを確認する**

Supabase Local が必要。起動していなければ `supabase start`。

Run: `uv run --project apps/api pytest apps/api/tests/integration/test_capture_repository.py -m integration -k "search or by_ids" -v`
Expected: FAIL（`AttributeError: 'CaptureRepository' object has no attribute 'list_search_documents'`）。DB が無い場合は skip されるので、その場合は Step 4 の実装後に `pytest apps/api/tests` が GREEN であることだけで進める。

- [x] **Step 3: repository の import を直す**

`apps/api/src/hibi/modules/captures/repository.py` の先頭に足す。

```python
import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID
```

`hibi.modules.captures.policies` の import の下（isort の辞書順で `policies` < `search` < `types`）に足す。

```python
from hibi.modules.captures.search import SearchDocument
```

- [x] **Step 4: 読み出しを 2 つ足す**

`list_for_user` の下に足す。

```python
    async def list_search_documents(self, user_id: UUID) -> list[SearchDocument]:
        """検索の候補を読み出す。所有者の completed 行だけを返す。

        embedding が無い行も候補に残す。outer join を使う。キーワード検索は
        embedding を使わないので、無い行も当たる必要がある。意味検索は
        search.py 側で embedding が無い行を除く。

        Args:
            user_id: 所有者。別ユーザーの行は読まない。

        Returns:
            新しい順の SearchDocument。
        """
        stmt = (
            select(CaptureModel, CaptureEmbeddingModel)
            .outerjoin(
                CaptureEmbeddingModel,
                CaptureEmbeddingModel.capture_id == CaptureModel.id,
            )
            .where(
                CaptureModel.user_id == user_id,
                CaptureModel.status == CAPTURE_STATUS_COMPLETED,
            )
            .order_by(CaptureModel.created_at.desc(), CaptureModel.id.desc())
        )
        result = await self._session.execute(stmt)
        return [
            SearchDocument(
                capture_id=row.id,
                user_id=row.user_id,
                status=row.status,
                text=row.raw_text,
                embedding=_to_embedding(embedding_row),
            )
            for row, embedding_row in result.all()
        ]

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        """id の一覧から、所有者の Capture を scenario 付きで読む。

        scenario は outer join で1回のクエリにまとめる。scenario は capture_id が
        主キーなので、join しても行は増えない。scenario が無い Capture も返す。
        返す順序は保証しない。SQL の IN は順序を持たない。呼び出し側が
        順位に合わせて並べ直す。所有者が違う id は黙って落とす。

        Args:
            user_id: 所有者。
            capture_ids: 読みたい Capture の id。空なら DB を叩かず空を返す。

        Returns:
            見つかった Capture。
        """
        if not capture_ids:
            return []

        stmt = (
            select(CaptureModel, CaptureScenarioModel)
            .outerjoin(
                CaptureScenarioModel,
                CaptureScenarioModel.capture_id == CaptureModel.id,
            )
            .where(CaptureModel.user_id == user_id, CaptureModel.id.in_(capture_ids))
        )
        result = await self._session.execute(stmt)
        return [_to_capture(row, scenario_row) for row, scenario_row in result.all()]
```

ファイル末尾の `_to_capture` の下に変換関数を足す。

```python
def _to_embedding(row: CaptureEmbeddingModel | None) -> Embedding | None:
    """embedding の行を値オブジェクトに変換する。行が無ければ None。"""
    if row is None:
        return None
    return Embedding(
        vector=tuple(row.embedding),
        model=row.embedding_model,
        dimensions=row.embedding_dimensions,
        version=row.embedding_version,
    )
```

- [x] **Step 5: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/integration/test_capture_repository.py -m integration -k "search or by_ids" -v`
Expected: 全 PASS（DB が無ければ skip）

- [x] **Step 6: 通常の pytest と型を通す**

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
uv run --project apps/api pytest apps/api/tests
```

Expected: 4 つとも PASS。Task 1 Step 6 で出ていた `unresolved-attribute` 2 件が消えている。

- [x] **Step 7: Commit**

```bash
git add apps/api/src/hibi/modules/captures/repository.py apps/api/tests/integration/test_capture_repository.py
git commit -m "feat(captures): read owner search documents and captures by id"
```

---

### Task 3: router に GET /search を足す

`q` と `mode` の検証は FastAPI の `Query` と `Literal` に任せる（`RequestValidationError` が既存の handler で problem+json の 422 になる）。path の登録位置が効くので、`/{capture_id}` の **前** に置く。

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/router.py`
- Test: `apps/api/tests/test_capture_api.py`

**Interfaces:**

- Consumes: `CaptureService.search_captures(query) -> list[Capture]`（Task 1）、`SearchCapturesQuery`、`CaptureSearchMode`、`CAPTURE_SEARCH_MODE_KEYWORD`、既存の `_to_capture_response`、`ApiResponse[list[CaptureResponse]]`
- Produces: `GET /api/v1/captures/search`（`operation_id="searchCaptures"`）

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/test_capture_api.py` を 2 箇所直す。

`FakeCaptureService` に検索を足す（`list_captures` の下）。import に `SearchCapturesQuery` を足す。

```python
    async def search_captures(self, query: SearchCapturesQuery) -> list[Capture]:
        self.search_calls.append((query.q, query.mode))
        return [
            capture
            for capture in self.captures.values()
            if capture.user_id == query.user_id and query.q in capture.raw_text
        ]
```

`FakeCaptureService.__init__` に記録用の list を足す。

```python
        self.search_calls: list[tuple[str, str]] = []
```

ファイル末尾にテストを足す。

```python
def test_search_captures_returns_matching_captures() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["data"]] == [str(CAPTURE_ID)]
    assert fake.search_calls == [("牛乳", "keyword")]


def test_search_captures_passes_the_requested_mode() -> None:
    fake = FakeCaptureService()

    response = _client(fake).get(
        "/api/v1/captures/search", params={"q": "ミルク", "mode": "semantic"}
    )

    assert response.status_code == 200
    assert fake.search_calls == [("ミルク", "semantic")]


def test_search_captures_returns_an_empty_array_without_hits() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).get("/api/v1/captures/search", params={"q": "記事"})

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_search_captures_does_not_return_other_owners() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed", user_id=OTHER_ID)

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "あ" * 201},
        {"q": "牛乳", "mode": "bogus"},
    ],
    ids=["missing_q", "blank_q", "too_long_q", "bad_mode"],
)
def test_search_captures_rejects_invalid_query(params: dict[str, str]) -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/search", params=params)

    assert response.status_code == 422
    assert fake.search_calls == []


def test_search_captures_requires_a_token() -> None:
    response = _client(FakeCaptureService(), authenticated=False).get(
        "/api/v1/captures/search", params={"q": "牛乳"}
    )

    assert response.status_code == 401


def test_search_path_is_registered_before_the_capture_id_path() -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    # /{capture_id}が先に当たると"search"のUUIDパースで422になる
    assert response.status_code == 200
```

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_api.py -k search -v`
Expected: `404` または `422`（`/search` が未登録、または `/{capture_id}` に吸われる）で FAIL

- [x] **Step 3: router に endpoint を足す**

`apps/api/src/hibi/modules/captures/router.py` の import に足す。

```python
from hibi.modules.captures.types import (
    CAPTURE_SEARCH_MODE_KEYWORD,
    Capture,
    CaptureScenario,
    CaptureSearchMode,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    UpdateCaptureCommand,
)
```

先頭の import に `from typing import Annotated` を足す（`from uuid import UUID` の上）。

`@router.get("/{capture_id}", ...)` のブロックの **直前** に足す。

```python
@router.get(
    "/search",
    operation_id="searchCaptures",
    response_model=ApiResponse[list[CaptureResponse]],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def search_captures(
    q: str = Query(min_length=1, max_length=200),
    mode: Annotated[CaptureSearchMode, Query()] = CAPTURE_SEARCH_MODE_KEYWORD,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """完了した記録を、自分の分だけ検索する。

    mode=keyword は本文の語の重なり、mode=semantic は意味の近さで選ぶ。
    近い順に最大20件を返し、見つからなければ空配列を返す。
    """
    query = SearchCapturesQuery(user_id=principal.user_id, q=q, mode=mode)
    captures = await service.search_captures(query)
    return ApiResponse(data=[_to_capture_response(capture) for capture in captures])
```

- [x] **Step 4: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_api.py -v`
Expected: 全 PASS

- [x] **Step 5: 全部通すことを確認する**

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
uv run --project apps/api pytest apps/api/tests
```

Expected: 4 つとも PASS

- [x] **Step 6: Commit**

```bash
git add apps/api/src/hibi/modules/captures/router.py apps/api/tests/test_capture_api.py
git commit -m "feat(captures): search captures over HTTP for the owner only"
```

---

### Task 4: OpenAPI と client を再生成する

契約の正本 `contracts/openapi.json` と `packages/api-client` を、同じ変更で更新する。

**Files:**

- Modify: `contracts/openapi.json`（生成物）
- Modify: `packages/api-client` 配下の生成物

**Interfaces:**

- Consumes: Task 3 の `operation_id="searchCaptures"`
- Produces: client の `searchCaptures`（web は実装順 5 で使う）

- [x] **Step 1: 再生成する**

```bash
just openapi
```

- [x] **Step 2: 差分が検索分だけか確認する**

```bash
git status --short contracts packages
git diff contracts/openapi.json | head -60
```

Expected: `/api/v1/captures/search` の path と `searchCaptures` の追加だけ。既存 path の差分は出ない。

router の docstring は FastAPI が `description` として `openapi.json` に出す。`searchCaptures` の `description` に Task 3 の docstring（「完了した記録を、自分の分だけ検索する。…」）が入っていること、client の生成物にもコメントとして入ることを確認する。他の endpoint には description が無いので、検索だけに付くのは意図どおり。

- [x] **Step 3: web 側が壊れていないことを確認する**

```bash
corepack pnpm typecheck
corepack pnpm build
```

Expected: どちらも PASS（画面は実装順 5 なのでまだ `searchCaptures` を呼ばない）

- [x] **Step 4: Commit**

```bash
git add contracts packages
git commit -m "feat(contracts): regenerate the client for capture search"
```

- [x] **Step 5: check を全部通す**

```bash
just check
```

Expected: 全部 PASS

---

## 完了条件（この計画のぶん）

- [ ] `GET /api/v1/captures/search?q=牛乳` が `牛乳を買う` を返す
- [ ] `q=記事` が `あとで読む記事` を返す
- [ ] `q=ミルク&mode=semantic` が `牛乳を買う` を返し、`mode=keyword` では 0 件
- [ ] `q=ランチ&mode=semantic` の上位が `牛乳を買う` にならない
- [ ] 別ユーザーの同じ本文は、どちらの検索にも出ない
- [ ] `pending`、`processing`、`failed` は検索対象にならない
- [ ] 0 件は 200 と空配列（404 にしない）
- [ ] `q` が空、201 文字、`mode` が不正なら 422
- [ ] 近い順に最大 20 件
- [ ] 検索は Capture 本文の embedding を作り直さない（クエリ文のベクトル化だけ）
- [ ] `/search` が `/{capture_id}` より前に登録されている
- [ ] `contracts/openapi.json` と `packages/api-client` が再生成済み
- [ ] `just check` が GREEN

## 先送り（この計画に含めない）

| 先送り | 行き先 |
| --- | --- |
| 一覧の上の検索欄、「検索しています」「見つかりませんでした」 | 実装順 5 |
| 検索結果を使った回答生成 | Week 10 |
| HNSW index、pgvector への順位付けの押し下げ | 計測してから。Week 8 の「やらないこと」 |
| 日付や route での絞り込み | Week 8 の「やらないこと」 |
| embedding の自動 backfill | Week 8 の「やらないこと」 |

## 判断メモ

- **順位付けを Python に残す理由**: 実装順 1 で `search.py` の 2 関数をテスト付きで作った。pgvector の `<=>` に押し下げるとそのテストが使えなくなり、キーワード検索の TF-IDF は SQL では書き直しになる。仕様が「件数が小さい。計測前に足さない」と言っているので、`completed` 行を全部読んで Python で並べる。重くなったら `list_search_documents` の中だけを置き換えれば済む形にしてある。
- `list_captures_by_ids` **を分けた理由**: `SearchDocument` は順位付けに必要な最小限（本文と embedding）しか持たない。レスポンスには scenario 付きの `Capture` が必要なので、上位 20 件だけ読み直す。全件に scenario を join すると、捨てる 20 件以外のぶんが無駄になる。
- **scenario は outer join の 1 クエリ**: `capture_scenarios` は `capture_id` が主キーで Capture と多くて 1 対 1 なので、join しても行が増えない。`list_for_user` は「Capture を取ってから `IN` で scenario を取る」2 回の形だが、そこに揃えない。2 回にする利点が無く、往復と突き合わせの `dict` が余計になる。`list_for_user` は範囲外なので触らない。
- **空白だけの** `q`: 仕様の「`q` は 1 文字以上」に従い、`Query(min_length=1)` だけで判定する。空白 1 文字は valid な入力として 200 と空配列を返す（tokenize が空になるので 0 件）。`.strip()` を挟んで 422 にはしない。
- `mode` **の型**: `CaptureSearchMode = Literal["keyword", "semantic"]` を `types.py` に置き、router の annotation に使う。OpenAPI に enum として出るので、client 側も 2 値に絞られる。
- **順序の正本**: SQL の `IN` は順序を保証しないので、service が ranker の並びで並べ直す。`list_captures_by_ids` には `order_by` を付けない（付けても service が上書きする）。
- **意味検索のランチのテスト**: fake embedder の固定ベクトルは本文の完全一致でだけ効く。単独の `ランチ` は固定の対象外で、hash で次元 0 に落ちて `牛乳を買う` の固定ベクトルと同一になり、cosine 1.0 で牛乳が 1 位になる（8 バケットの衝突）。service の不具合ではなく fake の性質なので、テストは固定ベクトルを持つ `ランチ 1200 円` で引き、結果が `ランチ 1200 円` の 1 件だけであることを厳密に確かめる。fake の固定ベクトルは仕様どおり 5 本文のままにし、足さない。
- **docstring の方針**: 公開する入口（`SearchCapturesQuery`、`search_captures` の service / router、repository の 2 メソッド、`_to_embedding`）に付ける。形式は Google スタイル（`Args:` / `Returns:`）、言語は既存のコメントと docs に合わせて日本語。1 行で足りるもの（`_to_embedding`）は 1 行にする。書く内容は「何をするか」より、呼び出し側が知らないと困る性質（順序を保証しない、embedding が無い行も残す、0 件は例外にしない）を優先する。**router の docstring は OpenAPI の** `description` **に出て client にも入る**ので、内部事情（TF-IDF、embedder）ではなく API 利用者向けの文だけにしてある。
- `mode` **を** `Annotated` **で書く理由**: `mode: CaptureSearchMode = Query(default=...)` は B008 で落ちる。ruff の B008 は注釈が `str` や `int` のような不変型だと既定値の呼び出しを許すが、`CaptureSearchMode` は別の場所で定義した `Literal` の別名で、ruff には不変型と判別できない。`q: str = Query(...)` や既存の `limit: int = Query(...)` が通るのはこのため。`extend-immutable-calls` に `fastapi.Query` を足すと全体の設定が変わるので、`Annotated[CaptureSearchMode, Query()] = CAPTURE_SEARCH_MODE_KEYWORD` と書く。既定値が Query の呼び出しではなく定数になり、FastAPI 公式の推奨形でもある。OpenAPI の出力は変わらない。
- **全角括弧の扱い**: docstring の全角括弧 `（` `）` は RUF002、コメントでは RUF003 になる。括弧を使わない文に言い換え、`noqa` では黙らせない。全角の `、` `。` は対象外。
