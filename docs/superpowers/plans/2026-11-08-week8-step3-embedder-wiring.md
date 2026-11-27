# Week 8 実装順 3: process_capture から embedder を呼ぶ 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `process_capture` が完了更新と同じトランザクションで embedding を 1 回だけ作り、`HIBI_OPEN_AI_EMBEDDING_API_KEY` が空なら `FakeTextEmbedder`、入っていれば `ProviderTextEmbedder` を使う。

**Architecture:** `TextEmbedder` port は [`apps/api/src/hibi/ai/embedding.py`](../../../apps/api/src/hibi/ai/embedding.py) にすでにある。実装を 2 つ（既存の `FakeTextEmbedder` と、新規の `ProviderTextEmbedder`）揃え、既存の `classifier_factory` と同じ「キーが空なら fake」の形で `build_text_embedder()` を足す。`CaptureService` は port だけを受け取り、`has_same_content_embedding` が真なら embedder を呼ばない。SDK 型は `provider_embedder.py` の外に漏らさない。

**Tech Stack:** Python 3.14 / FastAPI / SQLAlchemy 2 (asyncio) / arq / openai SDK / pgvector / pytest + pytest-asyncio / ruff / ty

**参照仕様:** [docs/architecture/26-week8-search.md](../../architecture/26-week8-search.md)（「Port」「障害」「テスト」「実装順 3」）

## Global Constraints

- Python は `>=3.14,<3.15`。`target-version = "py314"`。
- ruff は `line-length = 100`、lint は `E, F, I, UP, B, ASYNC, RUF`。整形は `ruff format`（black は使わない）。
- pytest の既定は `-m 'not integration'`、`asyncio_mode = "auto"`。
- 通常の pytest は Jev、LLM、embedding API を呼ばない。実 API を叩くテストは `@pytest.mark.integration`。
- 次元は `CAPTURE_EMBED_DIMENSIONS = 8` 固定。DB 列は `extensions.vector(8)`（[20261107075656_capture_embeddings.sql](../../../supabase/migrations/20261107075656_capture_embeddings.sql)）なので、provider も 8 次元で返す。
- version は `CAPTURE_EMBED_VERSION = "capture-embed-v1"`。fake の model は `capture-embed-fake-v1`。
- SDK 側の retry は無効（`max_retries=0`）。retry 回数の正本は job の 3 回（`CAPTURE_PROCESSING_MAX_ATTEMPTS`）。
- job 引数は `capture_id` と `processing_generation` のまま増やさない。
- 検索 API（実装順 4）と画面（実装順 5）はこの計画に含めない。

## 現状（2026-11-08 時点の baseline）

作業ツリーに未コミットの WIP がある。この計画はその続きとして書いてある。

- `apps/api/tests` は **44 failed / 131 passed**。原因は `CaptureService.__init__` に `embedder` を足したのに呼び出し元（job / router / テストの helper）を直していないこと。この 44 件は Task 4 と Task 5 まで残り続ける。途中の Task では「44 failed のまま、新しい失敗が増えていないこと」を見る。
- `core/config.py` に `open_ai_embedding_api_key` / `open_ai_embedding_base_url` / `open_ai_embedding_model` が入っている。この計画はこの 3 つを使う前提で進める。
- `repository.py` に `has_same_content_embedding()` が、`complete_capture_classification()` に `embedding` 引数が入っている。どちらもそのまま使う。
- `service.py` の分岐が反転している（`if existing:` のときに embed している）。Task 4 で直す。
- `config.py` / `repository.py` / `service.py` に、line-length 88 で整形し直した無関係な差分が混ざっている。Task 1 で戻す。

## File Structure

| ファイル | 役割 | 変更 |
| --- | --- | --- |
| `apps/api/src/hibi/ai/embedding.py` | port、定数、障害型 | `EmbeddingProviderError` を追加 |
| `apps/api/src/hibi/ai/provider_embedder.py` | 実 embedding。openai SDK をここだけに閉じる | 新規 |
| `apps/api/src/hibi/ai/fake_embedder.py` | CI 用の固定ベクトル | 変更なし |
| `apps/api/src/hibi/ai/classifier_factory.py` | キーの有無で実装を選ぶ | `build_text_embedder()` を追加 |
| `apps/api/src/hibi/modules/captures/service.py` | 同じ hash が無いときだけ embed | 分岐を修正 |
| `apps/api/src/hibi/jobs/process_capture_job.py` | worker 側の組み立て | `embedder=` を渡す |
| `apps/api/src/hibi/modules/captures/router.py` | API 側の組み立て | `embedder=` を渡す |
| `apps/api/.env.example` | 環境変数の見本 | 3 行追加 |

---

### Task 1: 整形ノイズを戻す

WIP に混ざった line-length 88 の整形差分を、リポジトリの 100 桁に戻す。これを先にやらないと、以降の差分レビューで本質の変更が埋もれる。

**Files:**

- Modify: `apps/api/src/hibi/core/config.py`
- Modify: `apps/api/src/hibi/modules/captures/repository.py`
- Modify: `apps/api/src/hibi/modules/captures/service.py`

**Interfaces:**

- Consumes: なし
- Produces: なし（整形だけ）

- [x] **Step 1: 整形が崩れていることを確認する**

Run: `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`
Expected: `Would reformat: apps/api/src/hibi/core/config.py` などが出て非 0 終了

- [x] **Step 2: ruff format をかける**

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
```

- [x] **Step 3: 残った差分が意図した 3 点だけか確認する**

```bash
git diff --stat
git diff apps/api/src/hibi/core/config.py
```

Expected: `config.py` の差分は `open_ai_embedding_*` の 3 行追加だけ。`repository.py` は `import hashlib`、`CaptureEmbeddingModel` の import、`has_same_content_embedding`、`complete_capture_classification` の `embedding` 引数だけ。`allowed_jwt_algorithms` や `list_for_user` などの整形差分は消えている。

- [x] **Step 4: 整形と lint を通す**

Run: `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts && uv run --project apps/api ruff check apps/api/src apps/api/tests scripts`
Expected: どちらも PASS（`service.py` の 150 桁の行は Step 2 で折り返されているので E501 は出ない）

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/core/config.py apps/api/src/hibi/modules/captures/repository.py apps/api/src/hibi/modules/captures/service.py
git commit -m "style(captures): keep the 100 column format for the embedding work"
```

---

### Task 2: ProviderTextEmbedder を足す

実 embedding の実装。openai SDK の型と例外を `provider_embedder.py` の中だけに閉じる。パターンは [`llm_clarification.py`](../../../apps/api/src/hibi/ai/llm_clarification.py)（`ClarificationModelClient` / `SdkClarificationClient` / `LlmClarificationGenerator`）と揃える。

**Files:**

- Modify: `apps/api/src/hibi/ai/embedding.py`
- Create: `apps/api/src/hibi/ai/provider_embedder.py`
- Modify: `apps/api/.env.example`
- Test: `apps/api/tests/test_provider_embedder.py`（新規）
- Test: `apps/api/tests/test_provider_embedder_live.py`（新規）

**Interfaces:**

- Consumes: `hibi.ai.embedding.Embedding`、`CAPTURE_EMBED_DIMENSIONS`（= 8）、`CAPTURE_EMBED_VERSION`（= `"capture-embed-v1"`）、`hibi.core.config.get_settings`
- Produces:
  - `hibi.ai.embedding.EmbeddingProviderError`（`Exception` 派生、引数なし）
  - `hibi.ai.provider_embedder.EmbeddingModelClient`（Protocol）: `async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]`
  - `hibi.ai.provider_embedder.SdkEmbeddingClient`（上の実装）
  - `hibi.ai.provider_embedder.ProviderTextEmbedder(client: EmbeddingModelClient | None = None)`: `async def embed_text(self, text: str) -> Embedding`

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/test_provider_embedder.py` を新規作成する。

```python
from types import SimpleNamespace

import pytest
from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from pydantic import SecretStr

from hibi.ai import provider_embedder
from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    EmbeddingProviderError,
)
from hibi.ai.provider_embedder import ProviderTextEmbedder, SdkEmbeddingClient

_MODEL = "text-embedding-3-small"


class _Timeout(APITimeoutError):
    def __init__(self) -> None:
        Exception.__init__(self, "timeout")


class _Connection(APIConnectionError):
    def __init__(self) -> None:
        Exception.__init__(self, "connection")


class _RateLimit(RateLimitError):
    def __init__(self) -> None:
        Exception.__init__(self, "rate limit")


class _InternalServer(InternalServerError):
    def __init__(self) -> None:
        Exception.__init__(self, "internal server error")


class FakeEmbeddingClient:
    def __init__(self, result: list[float] | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, str, int]] = []

    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]:
        self.calls.append((text, model, dimensions))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class FakeAsyncOpenAI:
    def __init__(
        self,
        *,
        result: list[float] | None = None,
        error: Exception | None = None,
        **kwargs: object,
    ) -> None:
        del kwargs
        self._result = result
        self._error = error

    @property
    def embeddings(self) -> FakeAsyncOpenAI:
        return self

    async def create(self, **kwargs: object) -> object:
        del kwargs
        if self._error is not None:
            raise self._error
        return SimpleNamespace(data=[SimpleNamespace(embedding=self._result)])


@pytest.fixture(autouse=True)
def _embedding_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_embedder,
        "get_settings",
        lambda: SimpleNamespace(
            open_ai_embedding_api_key=SecretStr("test-key"),
            open_ai_embedding_base_url="",
            open_ai_embedding_model=_MODEL,
            open_ai_timeout_seconds=30.0,
        ),
    )


@pytest.mark.asyncio
async def test_provider_embedder_returns_the_vector_with_fixed_dimensions() -> None:
    client = FakeEmbeddingClient([0.5] * CAPTURE_EMBED_DIMENSIONS)

    embedding = await ProviderTextEmbedder(client).embed_text("牛乳を買う")

    assert embedding.vector == tuple([0.5] * CAPTURE_EMBED_DIMENSIONS)
    assert embedding.model == _MODEL
    assert embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert embedding.version == CAPTURE_EMBED_VERSION
    assert client.calls == [("牛乳を買う", _MODEL, CAPTURE_EMBED_DIMENSIONS)]


@pytest.mark.asyncio
@pytest.mark.parametrize("vector", [[], [0.1] * 7, [0.1] * 9])
async def test_provider_embedder_rejects_other_dimensions(vector: list[float]) -> None:
    with pytest.raises(EmbeddingProviderError):
        await ProviderTextEmbedder(FakeEmbeddingClient(vector)).embed_text("牛乳を買う")


@pytest.mark.asyncio
async def test_provider_embedder_reraises_provider_error() -> None:
    with pytest.raises(EmbeddingProviderError):
        await ProviderTextEmbedder(FakeEmbeddingClient(EmbeddingProviderError())).embed_text(
            "牛乳を買う"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [_Timeout(), _Connection(), _RateLimit(), _InternalServer()],
    ids=["timeout", "connection", "rate_limit", "internal_server"],
)
async def test_sdk_client_maps_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=error, **kwargs),
    )

    with pytest.raises(EmbeddingProviderError):
        await SdkEmbeddingClient().create_embedding(
            text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
        )


@pytest.mark.asyncio
async def test_sdk_client_does_not_map_non_transient_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(error=RuntimeError("bad request"), **kwargs),
    )

    with pytest.raises(RuntimeError, match="bad request"):
        await SdkEmbeddingClient().create_embedding(
            text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
        )


@pytest.mark.asyncio
async def test_sdk_client_returns_the_first_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hibi.ai.provider_embedder.AsyncOpenAI",
        lambda **kwargs: FakeAsyncOpenAI(result=[0.25] * CAPTURE_EMBED_DIMENSIONS, **kwargs),
    )

    vector = await SdkEmbeddingClient().create_embedding(
        text="牛乳を買う", model=_MODEL, dimensions=CAPTURE_EMBED_DIMENSIONS
    )

    assert vector == [0.25] * CAPTURE_EMBED_DIMENSIONS
```

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_provider_embedder.py -v`
Expected: collection error（`ModuleNotFoundError: No module named 'hibi.ai.provider_embedder'` と `ImportError: cannot import name 'EmbeddingProviderError'`）

- [x] **Step 3: 障害型を足す**

`apps/api/src/hibi/ai/embedding.py` の `Embedding` の下、`TextEmbedder` の上に足す。

```python
@dataclass
class EmbeddingProviderError(Exception):
    pass
```

- [x] **Step 4: ProviderTextEmbedder を書く**

`apps/api/src/hibi/ai/provider_embedder.py` を新規作成する。

```python
from typing import Protocol

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    Embedding,
    EmbeddingProviderError,
)
from hibi.core.config import get_settings


class EmbeddingModelClient(Protocol):
    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]: ...


class SdkEmbeddingClient:
    async def create_embedding(self, *, text: str, model: str, dimensions: int) -> list[float]:
        client = AsyncOpenAI(
            api_key=get_settings().open_ai_embedding_api_key.get_secret_value(),
            base_url=get_settings().open_ai_embedding_base_url or None,
            timeout=get_settings().open_ai_timeout_seconds,
            max_retries=0,
        )
        try:
            response = await client.embeddings.create(
                model=model,
                input=text,
                dimensions=dimensions,
            )
        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as error:
            raise EmbeddingProviderError() from error
        return list(response.data[0].embedding)


class ProviderTextEmbedder:
    def __init__(self, client: EmbeddingModelClient | None = None) -> None:
        self._client = client or SdkEmbeddingClient()

    async def embed_text(self, text: str) -> Embedding:
        model = get_settings().open_ai_embedding_model
        vector = await self._client.create_embedding(
            text=text,
            model=model,
            dimensions=CAPTURE_EMBED_DIMENSIONS,
        )
        if len(vector) != CAPTURE_EMBED_DIMENSIONS:
            raise EmbeddingProviderError()
        return Embedding(
            vector=tuple(float(value) for value in vector),
            model=model,
            dimensions=CAPTURE_EMBED_DIMENSIONS,
            version=CAPTURE_EMBED_VERSION,
        )
```

- [x] **Step 5: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_provider_embedder.py -v`
Expected: 全 PASS（network は張らない）

- [x] **Step 6: 実 API を叩く integration テストを書く**

`apps/api/tests/test_provider_embedder_live.py` を新規作成する。既定の pytest からは `-m 'not integration'` で外れる。

既存の live テスト（`tests/integration/test_llm_clarification_live.py`）は `tests/integration/` 配下にある。揃えるなら `git mv apps/api/tests/test_provider_embedder_live.py apps/api/tests/integration/` で移す。マーカーが効いているので除外動作はどちらでも同じ。

```python
import pytest

from hibi.ai.embedding import CAPTURE_EMBED_DIMENSIONS, CAPTURE_EMBED_VERSION
from hibi.ai.provider_embedder import ProviderTextEmbedder
from hibi.core.config import get_settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_provider_embedder_returns_a_vector() -> None:
    if not get_settings().open_ai_embedding_api_key.get_secret_value().strip():
        pytest.skip("HIBI_OPEN_AI_EMBEDDING_API_KEY is not configured")

    embedding = await ProviderTextEmbedder().embed_text("牛乳を買う")

    assert embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert len(embedding.vector) == CAPTURE_EMBED_DIMENSIONS
    assert embedding.version == CAPTURE_EMBED_VERSION
    assert any(value != 0.0 for value in embedding.vector)
```

- [x] **Step 7: integration が既定の pytest から外れていることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests 2>&1 | tail -3`
Expected: `deselected` の件数が 29 から 30 に増えている（失敗数は Task 1 のまま 44 で変わらない）

- [x] **Step 8: .env.example に 3 行足す**

`apps/api/.env.example` の末尾（`HIBI_OPEN_AI_TIMEOUT_SECONDS=30.0` の下）に空行を挟んで足す。

```
HIBI_OPEN_AI_EMBEDDING_API_KEY=sk-example
HIBI_OPEN_AI_EMBEDDING_BASE_URL=https://api.openai.com/v1
HIBI_OPEN_AI_EMBEDDING_MODEL=text-embedding-3-small
```

- [x] **Step 9: 整形と型を通す**

まず整形をかけてから確認する（`--check` は差分を出すだけで直さない）。

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
```

Expected: `ruff format --check` と `ruff check` は PASS。`ty check` は **Task 5 まで `missing-argument: embedder` の 3 件（`process_capture_job.py:34`、`:47`、`router.py:39`）が残る**。この 3 件以外の診断が出ていないことだけ確認する。

- [x] **Step 10: Commit**

```bash
git add apps/api/src/hibi/ai/embedding.py apps/api/src/hibi/ai/provider_embedder.py apps/api/tests/test_provider_embedder.py apps/api/tests/test_provider_embedder_live.py apps/api/.env.example
git commit -m "feat(ai): embed capture text with the embedding provider"
```

---

### Task 3: build_text_embedder を足す

キーが空なら fake、入っていれば provider。`classifier_factory.py` は既に `build_capture_classifier` と `build_clarification_generator` を持っていて、同じ「キーの有無で選ぶ」役目なのでここに置く。

**Files:**

- Modify: `apps/api/src/hibi/ai/classifier_factory.py`
- Test: `apps/api/tests/test_classifier_factory.py:1-54`

**Interfaces:**

- Consumes: `hibi.ai.embedding.TextEmbedder`、`hibi.ai.fake_embedder.FakeTextEmbedder`、`hibi.ai.provider_embedder.ProviderTextEmbedder`（Task 2）、`hibi.core.config.get_settings`
- Produces: `hibi.ai.classifier_factory.build_text_embedder() -> TextEmbedder`

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/test_classifier_factory.py` を 2 箇所直す。

まず先頭の import ブロックを次の形にする。`build_text_embedder` を既存の `from hibi.ai.classifier_factory import (...)` に足し、`fake_embedder` と `provider_embedder` を ruff の isort（`I`）の辞書順の位置に入れる（`fake_embedder` は `fake_classifier` の下、`provider_embedder` は `llm_clarification` の下）。

```python
from types import SimpleNamespace

from pydantic import SecretStr

from hibi.ai import classifier_factory
from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import FakeTextEmbedder
from hibi.ai.jev_classifier import JevCaptureClassifier
from hibi.ai.llm_clarification import LlmClarificationGenerator
from hibi.ai.provider_embedder import ProviderTextEmbedder
```

次に、ファイル末尾にテストを 3 本足す。

```python
def test_build_text_embedder_uses_fake_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(open_ai_embedding_api_key=SecretStr("")),
    )

    assert isinstance(build_text_embedder(), FakeTextEmbedder)


def test_build_text_embedder_uses_fake_for_a_blank_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(open_ai_embedding_api_key=SecretStr("   ")),
    )

    assert isinstance(build_text_embedder(), FakeTextEmbedder)


def test_build_text_embedder_uses_provider_when_api_key_is_set(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(open_ai_embedding_api_key=SecretStr("test-key")),
    )

    assert isinstance(build_text_embedder(), ProviderTextEmbedder)
```

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_classifier_factory.py -v`
Expected: collection error（`ImportError: cannot import name 'build_text_embedder'`）

- [x] **Step 3: factory を書く**

`apps/api/src/hibi/ai/classifier_factory.py` を 2 箇所直す。

まず import ブロックを次の形にする（3 行追加。位置は isort の辞書順）。

```python
from hibi.ai.classification import CaptureClassifier, ClarificationGenerator
from hibi.ai.embedding import TextEmbedder
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import FakeTextEmbedder
from hibi.ai.jev_classifier import JevCaptureClassifier
from hibi.ai.llm_clarification import LlmClarificationGenerator
from hibi.ai.provider_embedder import ProviderTextEmbedder
from hibi.core.config import get_settings
```

次に、ファイル末尾に `build_text_embedder` を足す。

```python
def build_text_embedder() -> TextEmbedder:
    if get_settings().open_ai_embedding_api_key.get_secret_value().strip():
        return ProviderTextEmbedder()
    return FakeTextEmbedder()
```

- [x] **Step 4: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_classifier_factory.py -v`
Expected: 7 PASS

- [x] **Step 5: 整形と型を通す**

まず整形をかけてから確認する（`--check` は差分を出すだけで直さない）。

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
```

Expected: `ruff format --check` と `ruff check` は PASS。`ty check` は **Task 5 まで `missing-argument: embedder` の 3 件（`process_capture_job.py:34`、`:47`、`router.py:39`）が残る**。この 3 件以外の診断が出ていないことだけ確認する。

- [x] **Step 6: Commit**

```bash
git add apps/api/src/hibi/ai/classifier_factory.py apps/api/tests/test_classifier_factory.py
git commit -m "feat(ai): choose the fake embedder when the api key is empty"
```

---

### Task 4: process_capture から embedder を呼ぶ

同じ hash が既にあるときと本文が空のときは embedder を呼ばない。WIP の反転した分岐（`if existing:` で embed している）を直す。

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/service.py`（`process_capture` の `scenario = propose_capture_scenario(...)` の直後）
- Test: `apps/api/tests/test_process_capture_service.py`

**Interfaces:**

- Consumes: `CaptureRepository.has_same_content_embedding(user_id, *, capture_id, text) -> bool`、`CaptureRepository.complete_capture_classification(..., embedding: Embedding | None = None)`、`TextEmbedder.embed_text(text) -> Embedding`、`hibi.ai.fake_embedder.FakeTextEmbedder`
- Produces: `CaptureService` が `process_capture` で `embedding` を `complete_capture_classification` に渡す

**注意:** hash の照合は `capture.raw_text` をそのまま渡す。`repository.has_same_content_embedding` は渡した `text` を、`complete_capture_classification` は `row.raw_text` を sha256 にかけるので、`.strip()` を挟むと 2 つの hash がずれる。`raw_text` は `create_capture` / `update_capture` の時点で strip 済み。

- [x] **Step 1: 失敗するテストを書く**

`apps/api/tests/test_process_capture_service.py` を 3 箇所直し、テストを 3 本足す。

まず import に 2 行足す。clarification と embedding の間に依存は無く、位置は ruff の isort（`I`）の辞書順で決まる。`embedding` は `classification` と `fake_clarification` の間、`fake_embedder` は `fake_classifier` と `metrics` の間に入る。並べ違えると `ruff check` が I001 で落ちる。

```python
from hibi.ai.classification import (
    CAPTURE_QUESTION_VERSION,
    CLARIFICATION_FALLBACK_TEXT,
    ClarificationProviderError,
    Classification,
    ClassificationTimeoutError,
)
from hibi.ai.embedding import (
    CAPTURE_EMBED_DIMENSIONS,
    CAPTURE_EMBED_VERSION,
    Embedding,
)
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.fake_embedder import CAPTURE_EMBED_FAKE_MODEL, FakeTextEmbedder
from hibi.ai.metrics import llm_call_count, reset_llm_call
```

| 名前 | 使う場所 |
| --- | --- |
| `Embedding` | `FakeProcessCaptureRepository.embedding` の型、`complete_capture_classification` の署名、`RecordingEmbedder.embed_text` の戻り型 |
| `CAPTURE_EMBED_DIMENSIONS` / `CAPTURE_EMBED_VERSION` / `CAPTURE_EMBED_FAKE_MODEL` | `test_process_capture_embeds_the_text_once_when_completed` の assert |
| `FakeTextEmbedder` | `_service` の既定 embedder と `RecordingEmbedder` の中身 |

`FakeProcessCaptureRepository.__init__` に引数と state を足す（`fail_processing` の次）。

```python
    def __init__(
        self,
        capture: Capture | None,
        *,
        allow_start: bool = True,
        fail_processing: bool = False,
        has_embedding: bool = False,
    ) -> None:
        self.capture = capture
        self.allow_start = allow_start
        self.fail_processing = fail_processing
        self.has_embedding = has_embedding
        self.transitions: list[tuple[str, str]] = []
        self.classifications: list[dict[str, object]] = []
        self.scenario: ScenarioProposal | None = None
        self.embedding: Embedding | None = None
        self.embedding_lookups: list[tuple[UUID, str]] = []

    async def has_same_content_embedding(
        self, user_id: UUID, *, capture_id: UUID, text: str
    ) -> bool:
        del user_id
        self.embedding_lookups.append((capture_id, text))
        return self.has_embedding
```

`FakeProcessCaptureRepository.complete_capture_classification` の署名に `embedding` を足し、`self.scenario = scenario` の隣で受け取る。

```python
        clarification_text: str | None = None,
        scenario: ScenarioProposal | None = None,
        embedding: Embedding | None = None,
    ) -> Capture | None:
```

```python
        self.scenario = scenario
        self.embedding = embedding
        return self.capture
```

`RecordingClassifier` の下に embedder の fake を足す。

```python
class RecordingEmbedder:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed_text(self, text: str) -> Embedding:
        self.texts.append(text)
        return await FakeTextEmbedder().embed_text(text)
```

`_service` ヘルパーに `embedder` を足す。

```python
def _service(
    repository: FakeProcessCaptureRepository,
    classifier: RecordingClassifier | ScriptedClassifier | FakeCaptureClassifier | None = None,
    generator: ScriptedGenerator | FakeClarificationGenerator | None = None,
    embedder: RecordingEmbedder | FakeTextEmbedder | None = None,
) -> CaptureService:
    return CaptureService(
        cast(AsyncSession, None),
        cast(CaptureRepository, repository),
        classifier or FakeCaptureClassifier(),
        generator or FakeClarificationGenerator(),
        embedder or FakeTextEmbedder(),
    )
```

ファイル末尾にテストを 3 本足す。

```python
@pytest.mark.asyncio
async def test_process_capture_embeds_the_text_once_when_completed() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == ["牛乳を買う"]
    assert repository.embedding_lookups == [(capture.id, "牛乳を買う")]
    assert repository.embedding is not None
    assert repository.embedding.vector == (1, 0, 0, 0, 0, 0, 0, 0)
    assert repository.embedding.model == CAPTURE_EMBED_FAKE_MODEL
    assert repository.embedding.dimensions == CAPTURE_EMBED_DIMENSIONS
    assert repository.embedding.version == CAPTURE_EMBED_VERSION


@pytest.mark.asyncio
async def test_process_capture_does_not_embed_the_same_content_again() -> None:
    capture = _capture()
    repository = FakeProcessCaptureRepository(capture, has_embedding=True)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == []
    assert repository.embedding is None
    assert repository.capture is not None
    assert repository.capture.status == CAPTURE_STATUS_COMPLETED


@pytest.mark.asyncio
async def test_process_capture_does_not_embed_blank_text() -> None:
    capture = _capture(raw_text="   ")
    repository = FakeProcessCaptureRepository(capture)
    embedder = RecordingEmbedder()

    await _service(repository, embedder=embedder).process_capture(capture.id, 1)

    assert embedder.texts == []
    assert repository.embedding_lookups == []
    assert repository.embedding is None
```

空本文（`"   "`）は `FakeCaptureClassifier` で `chat` / `0.5` になり route は `clarify`、`propose_capture_scenario` は `None` を返す。このテストは embedder の呼び出しだけを見る。

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_process_capture_service.py -v`
Expected: `test_process_capture_does_not_embed_the_same_content_again` と `test_process_capture_does_not_embed_blank_text` が FAIL（反転した分岐のため、embed すべきでない場合に embed し、embed すべき場合にしない）。`test_process_capture_embeds_the_text_once_when_completed` は `assert repository.embedding is not None` で FAIL。

- [x] **Step 3: service の分岐を直す**

`apps/api/src/hibi/modules/captures/service.py` の `scenario = propose_capture_scenario(...)` の直後、WIP の 4 行を次で置き換える。

```python
        embedding: Embedding | None = None
        if capture.raw_text.strip() != "":
            has_embedding = await self._repository.has_same_content_embedding(
                capture.user_id,
                capture_id=capture_id,
                text=capture.raw_text,
            )
            if not has_embedding:
                embedding = await self._embedder.embed_text(capture.raw_text)
```

`complete_capture_classification` の呼び出しは `embedding=embedding,`（末尾カンマ付き）のままにする。

- [x] **Step 4: テストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_process_capture_service.py -v`
Expected: 全 PASS

- [x] **Step 5: 整形と型を通す**

まず整形をかけてから確認する（`--check` は差分を出すだけで直さない）。

```bash
uv run --project apps/api ruff format apps/api/src apps/api/tests scripts
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
```

Expected: `ruff format --check` と `ruff check` は PASS。`ty check` は **Task 5 まで `missing-argument: embedder` の 3 件（`process_capture_job.py:34`、`:47`、`router.py:39`）が残る**。この 3 件以外の診断が出ていないことだけ確認する。

- [x] **Step 6: Commit**

```bash
git add apps/api/src/hibi/modules/captures/service.py apps/api/tests/test_process_capture_service.py
git commit -m "feat(captures): embed the capture text only when the content changed"
```

---

### Task 5: job と router に embedder を渡す

`CaptureService` の呼び出し元を全部直し、`apps/api/tests` を GREEN に戻す。Task 1 の baseline で落ちていた 44 件がここで 0 になる。

**Files:**

- Modify: `apps/api/src/hibi/jobs/process_capture_job.py:34-39` と `:47-52`
- Modify: `apps/api/src/hibi/modules/captures/router.py:35-43`
- Test: `apps/api/tests/test_capture_service.py:207-217`
- Test: `apps/api/tests/test_process_capture_job.py:37-46`、`:72-81`、`:119-128`

**Interfaces:**

- Consumes: `hibi.ai.classifier_factory.build_text_embedder`（Task 3）、`hibi.ai.fake_embedder.FakeTextEmbedder`
- Produces: なし

- [x] **Step 1: job の fake service に embedder を足す**

`apps/api/tests/test_process_capture_job.py` の `FakeService` と 2 つの `FailingService`、計 3 つの `__init__` 署名に `embedder: object,` を `generator: object,` の下に足す。3 箇所目（`:119-128`）は `del classifier` を `del classifier, embedder` にする。

```python
        def __init__(
            self,
            *,
            session: object,
            repository: object,
            classifier: object,
            generator: object,
            embedder: object,
        ) -> None:
            pass
```

- [x] **Step 2: テストが落ちることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_process_capture_job.py -v`
Expected: FAIL（`TypeError: ... missing 1 required keyword-only argument: 'embedder'`）

- [x] **Step 3: job から embedder を渡す**

`apps/api/src/hibi/jobs/process_capture_job.py` の import を直す。

```python
from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
```

`CaptureService(...)` の 2 箇所（成功パスと `mark_processing_failed` のパス）どちらにも `embedder=build_text_embedder(),` を `generator=...` の下に足す。

```python
            service = CaptureService(
                session=session,
                repository=CaptureRepository(session=session),
                classifier=build_capture_classifier(),
                generator=build_clarification_generator(),
                embedder=build_text_embedder(),
            )
```

- [x] **Step 4: job のテストが通ることを確認する**

Run: `uv run --project apps/api pytest apps/api/tests/test_process_capture_job.py -v`
Expected: 全 PASS（`build_text_embedder()` はキー無しで `FakeTextEmbedder` を返すので network しない）

- [x] **Step 5: router から embedder を渡す**

`apps/api/src/hibi/modules/captures/router.py` の import を直す。

```python
from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
```

`_get_capture_service` に足す。

```python
    return CaptureService(
        session=session,
        repository=repository,
        classifier=build_capture_classifier(),
        generator=build_clarification_generator(),
        embedder=build_text_embedder(),
    )
```

- [x] **Step 6: service テストの helper に embedder を渡す**

`apps/api/tests/test_capture_service.py` の import に足す。

```python
from hibi.ai.fake_embedder import FakeTextEmbedder
```

`_service` の `CaptureService(...)` を直す。

```python
    return (
        CaptureService(
            session,
            repository,
            FakeCaptureClassifier(),
            FakeClarificationGenerator(),
            FakeTextEmbedder(),
        ),
        repository,
        session,
    )  # type: ignore[arg-type]
```

- [x] **Step 7: API も含めて全部通すことを確認する**

Run: `uv run --project apps/api pytest apps/api/tests`
Expected: `0 failed`（baseline の 44 failed が 0 になる。新規テストぶんで passed は 131 より増え、deselected は 30）

- [x] **Step 8: check を全部通す**

```bash
uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts
uv run --project apps/api ruff check apps/api/src apps/api/tests scripts
uv run --project apps/api ty check apps/api/src
uv run --project apps/api pytest apps/api/tests
```

Expected: 4 つとも PASS

- [x] **Step 9: OpenAPI が変わっていないことを確認する**

この Task は endpoint を足さないので、生成物に差分は出ないはず。

```bash
just openapi
git status --short contracts packages
```

Expected: `contracts` と `packages` に差分なし（差分が出たら未コミットの生成物があるということなので、別コミットに分ける）

- [x] **Step 10: Commit**

```bash
git add apps/api/src/hibi/jobs/process_capture_job.py apps/api/src/hibi/modules/captures/router.py apps/api/tests/test_capture_service.py apps/api/tests/test_process_capture_job.py
git commit -m "feat(captures): build the text embedder for the job and the api"
```

---

## 完了条件（この計画のぶん）

- [ ] `HIBI_OPEN_AI_EMBEDDING_API_KEY` が空のとき `build_text_embedder()` は `FakeTextEmbedder` を返す
- [ ] キーが入っているとき `ProviderTextEmbedder` を返し、8 次元・`capture-embed-v1` の `Embedding` を作る
- [ ] `process_capture` は完了更新と同じ呼び出しで embedding を渡す
- [ ] 同じ本文の再処理では embedder の呼び出しが増えない
- [ ] 本文が空なら embedder を呼ばない
- [ ] embedding の timeout / 接続失敗 / 429 / 5xx は `EmbeddingProviderError` になり、job の retry（3 回）に乗る
- [ ] 通常の pytest は embedding API を呼ばない。実 API のテストは `integration`
- [ ] `ruff format --check` / `ruff check` / `ty check` / `pytest` が GREEN

## 先送り（この計画に含めない）

| 先送り | 行き先 |
| --- | --- |
| `GET /api/v1/captures/search` と OpenAPI 再生成 | 実装順 4 |
| 一覧上の検索欄 | 実装順 5 |
| embedding の backfill ジョブ | Week 8 の「やらないこと」 |
| `render.yaml` への embedding キー追加 | 実運用で provider を有効にするとき（現状 `render.yaml` に `HIBI_OPEN_AI_API_KEY` も無い） |

## 判断メモ

- **8 次元のまま実 provider を使う件**: DB 列が `extensions.vector(8)`、`CAPTURE_EMBED_DIMENSIONS` も 8 なので、provider にも `dimensions=8` を要求する。`text-embedding-3-`* は `dimensions` 引数で短縮できるが、8 次元の意味検索の精度は実用水準ではない。Week 8 の完了条件（fake での順位）は満たすが、実 provider を本番で使う段では次元と列の拡張が必要になる。計画はこの前提を変えず、`len(vector) != 8` を `EmbeddingProviderError` にして、ずれたまま保存されるのを防ぐ。
- **設定を 3 つに分けた件**: WIP の `open_ai_embedding_api_key` / `_base_url` / `_model` をそのまま使う。embedding だけ別 provider に向けられる。timeout は `open_ai_timeout_seconds` を共用して knob を増やさない。
- `build_text_embedder` **の置き場所**: `classifier_factory.py` は既に classifier 以外（`build_clarification_generator`）も持っているので、ファイル名より役目を優先してここに置く。別ファイルに分けるなら `ai/factory.py` への改名を伴うので、この計画では触らない。
