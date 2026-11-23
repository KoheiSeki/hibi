# Week 10.5 評価の仕組みと hybrid 検索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 分類と route、検索の品質を、版の決まった評価データで測ってレポートに残し、Jev、商用の LLM、手元の open-weight モデルを同じ方法で比べられるようにする。検索に RRF の hybrid を足し、3 方式を数字で比べる。

**Architecture:** 評価は `hibi/evals/` に置き、Hibi の adapter と policy をそのまま呼ぶ。指標の計算は純粋関数に分け、run は分類器と embedder を引数で受けるので、テストは fake だけで回る。実モデルは `python -m hibi.evals` を手で実行し、レポート(Markdown と JSON)を `docs/ai/reports/` に commit する。

**Tech Stack:** Python 3.14、asyncio、Pydantic、OpenAI SDK(OpenAI 互換の接続先)、pytest(`asyncio_mode = "auto"`)、just。

**Spec:** `docs/architecture/30-week10-5-evaluation-and-hybrid-search.md`

## Global Constraints

- 通常の pytest と CI は外部の API を呼ばない。実モデルの評価は手で実行する
- 評価データは `docs/ai/evals/` に JSON Lines で置き、ファイル名に版を付ける(`-v1`)。既存の `capture-route-v1.jsonl` は fake 用の表なので、変えない、評価に使わない
- 評価データの正解は、Claude が案を作り、ユーザーが全件を確かめて確定する。`disputed` の tag が付いたケースは、指標から外し、件数だけ出す
- レポートは `docs/ai/reports/YYYY-MM-DD-<suite>-<label>.{md,json}`。本文は英語。API キーは書かない。base URL は host だけ
- 実行中の失敗(timeout)は再試行せず、失敗として数える。Ctrl-C ではレポートを書かない
- `LlmCaptureClassifier`: temperature 0、prompt の版 `capture-llm-classify-v1`。`hibi/ai/factory.py` に繋がない
- hybrid: RRF、`k = 60`、rank は 1 始まり、同点は capture ID の昇順。API の既定の mode は `keyword` のまま。画面は変えない
- 本番の embedding の次元(`vector(8)`)は変えない。評価だけ、次元を変えて測れる
- docstring は日本語の Google style(全角括弧を使わない、RUF002/003)。router は `Args:` と `Returns:` を付けない(CLAUDE.md)
- 実装の分担: Claude は RED のテストと評価データの案を書く。`src/` はユーザーが書く。Step 3 は layer ごとに、関数名と概要を箇条書きで書く(Week 10 と同じ形式)
- 検証は `uv run --project apps/api pytest apps/api/tests`、`uv run --project apps/api ruff check apps/api/src apps/api/tests scripts`、`ruff format --check`(同じ範囲)、`uv run --project apps/api ty check apps/api/src`。API の型を変えた Task は `just openapi` と `corepack pnpm typecheck`
- commit メッセージに `Co-Authored-By:` を付けない

## Review Focus

1. base URL にユーザー名やパスワードが入っていても、レポートには host しか出ない(キーの漏れ) → Task 4
2. 評価データの 1 行が壊れていると、モデルを 1 回も呼ばずに、ファイル名と行番号を示して止まる → Task 1、Task 4
3. Ctrl-C で止めたとき、途中までの結果をレポートとして残さない → Task 4
4. 同じ日に同じ label で 2 回実行しても、先のレポートを上書きしない → Task 4
5. 手元のモデルのサーバーが usage(トークン数)を返さなくても落ちず、トークン数は「不明」として出る → Task 5

## File Structure

| ファイル | 責務 |
| --- | --- |
| `apps/api/src/hibi/evals/__init__.py` (新規) | 空 |
| `apps/api/src/hibi/evals/datasets.py` (新規) | 評価データの読み込みと検証、`REPO_ROOT` と既定のパス |
| `apps/api/src/hibi/evals/metrics.py` (新規) | 指標の計算。純粋関数 |
| `apps/api/src/hibi/evals/report.py` (新規) | 実行の metadata、git の状態、レポートのパスと書き出し |
| `apps/api/src/hibi/evals/classification.py` (新規) | 分類の run、集計、Markdown |
| `apps/api/src/hibi/evals/search.py` (新規) | 検索の run、集計、Markdown |
| `apps/api/src/hibi/evals/__main__.py` (新規) | CLI |
| `apps/api/src/hibi/ai/usage.py` (新規) | LLM の呼び出し回数、トークン数、不正な出力の数を数える入れ物 |
| `apps/api/src/hibi/ai/llm_classifier.py` (新規) | `LlmCaptureClassifier` |
| `apps/api/src/hibi/ai/provider_embedder.py` (変更) | 次元を引数で受ける |
| `apps/api/src/hibi/modules/captures/{search,types,service,router}.py` (変更) | hybrid |
| `docs/ai/evals/capture-classification-v1.jsonl`、`capture-search-corpus-v1.jsonl`、`capture-search-queries-v1.jsonl` (新規) | 評価データ |
| `docs/ai/reports/` (新規) | レポート |
| `justfile` (変更) | `eval-classification`、`eval-search` |

---

### Task 1: 評価データの読み込みと検証

**Files:**

- Create: `apps/api/src/hibi/evals/__init__.py`、`apps/api/src/hibi/evals/datasets.py`
- Test: `apps/api/tests/test_eval_datasets.py`

**Interfaces:**

- Consumes: `hibi.modules.captures.policies.CAPTURE_CATEGORIES`
- Produces:
  - `REPO_ROOT: Path`(`Path(__file__).resolve().parents[5]`)、`EVALS_DIR = REPO_ROOT / "docs" / "ai" / "evals"`、`REPORTS_DIR = REPO_ROOT / "docs" / "ai" / "reports"`
  - `CLASSIFICATION_DATASET = EVALS_DIR / "capture-classification-v1.jsonl"`、`SEARCH_CORPUS = EVALS_DIR / "capture-search-corpus-v1.jsonl"`、`SEARCH_QUERIES = EVALS_DIR / "capture-search-queries-v1.jsonl"`
  - `DISPUTED_TAG = "disputed"`
  - `ClassificationCase(case_id: str, raw_text: str, expected_category: str, should_clarify: bool, tags: tuple[str, ...])`(frozen dataclass)
  - `SearchDocumentCase(doc_id: str, text: str)`、`SearchQueryCase(query_id: str, query: str, relevant_doc_ids: frozenset[str], tags: tuple[str, ...])`
  - `LoadedDataset[T](path: Path, sha256: str, cases: tuple[T, ...])`
  - `DatasetError(Exception)` — メッセージに、ファイル名と行番号(1 始まり)を含む
  - `load_classification_cases(path: Path) -> LoadedDataset[ClassificationCase]`
  - `load_search_dataset(corpus_path: Path, queries_path: Path) -> tuple[LoadedDataset[SearchDocumentCase], LoadedDataset[SearchQueryCase]]`

- [ ] **Step 1: Write the failing tests** in `tests/test_eval_datasets.py`(`tmp_path` にファイルを書いて読む)

```python
def test_loads_classification_cases_and_hashes_the_file(tmp_path): ...
    # 2 行 + 空行。cases の件数 2、tags は tuple、sha256 は hashlib.sha256(bytes).hexdigest() と一致

def test_rejects_an_unknown_category_with_the_line_number(tmp_path): ...
    # 2 行目が "expectedCategory": "learning" → DatasetError、str(error) に "line 2" とファイル名

def test_rejects_a_duplicate_case_id(tmp_path): ...            # "line 2" と "cls-001"
def test_rejects_a_missing_field_and_invalid_json(tmp_path): ...  # rawText 欠落、壊れた JSON の両方
def test_rejects_an_empty_raw_text(tmp_path): ...               # "   " も不可

def test_loads_the_search_corpus_and_queries(tmp_path): ...
    # relevant_doc_ids は frozenset

def test_rejects_a_query_whose_relevant_doc_is_not_in_the_corpus(tmp_path): ...
    # queries の line 1、"doc-999"

def test_rejects_a_query_without_relevant_docs(tmp_path): ...   # "relevantDocIds": []
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_datasets.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.evals`)

- [ ] **Step 3: Implement**

**evals**(`evals/datasets.py`)

- `load_classification_cases(path)`: バイト列を読み、SHA-256 を取る。行ごとに JSON を読み(空行は飛ばす)、必須の項目、型、category、ID の重複、空の本文を確かめる。最初の不正で `DatasetError(f"{path.name} line {n}: ...")`
- `load_search_dataset(corpus_path, queries_path)`: 2 つを同じ規則で読み、`relevantDocIds` が空でないこと、すべて corpus にあることを確かめる
- JSON の項目名(camelCase)と dataclass の名前(snake_case)の対応は、この file の中で閉じる

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_datasets.py -v`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/evals apps/api/tests/test_eval_datasets.py
git commit -m "feat(evals): load and validate versioned evaluation datasets"
```

---

### Task 2: 分類の評価データ

**Files:**

- Create: `docs/ai/evals/capture-classification-v1.jsonl`
- Test: `apps/api/tests/test_eval_datasets.py`(既存の file に 1 件足す)

**Interfaces:**

- Consumes: Task 1 の `load_classification_cases`、`CLASSIFICATION_DATASET`

- [ ] **Step 1: Write the failing test**

```python
def test_the_committed_classification_dataset_is_valid_and_balanced() -> None:
    dataset = load_classification_cases(CLASSIFICATION_DATASET)
    counts = Counter(case.expected_category for case in dataset.cases)
    assert len(dataset.cases) >= 60
    assert all(counts[category] >= 10 for category in CAPTURE_CATEGORIES)
    assert sum(case.should_clarify for case in dataset.cases) >= 10
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_datasets.py -v -k committed`
Expected: FAIL(`FileNotFoundError`)

- [ ] **Step 3: Claude が案を作る**

- 5 つの category を 10〜12 件ずつ、`shouldClarify: true` を 10〜12 件。ID は `cls-001` から連番
- tags は `basic`、`relative-date`、`amount`、`colloquial`、`notation`、`mixed`、`ambiguous` から付ける。各 category に `basic` 以外の tag を半分以上入れる
- `shouldClarify: true` の `expectedCategory` は、人が一番ありそうだと思う category にする(例: 「あれやっといて」は `chat`)

- [ ] **Step 4: ユーザーが全件を確かめて確定する**

迷った行は `disputed` を tags に足す(指標から外れる)。確定したら、Step 1 のテストを流す。
Run: `uv run --project apps/api pytest apps/api/tests/test_eval_datasets.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/ai/evals/capture-classification-v1.jsonl apps/api/tests/test_eval_datasets.py
git commit -m "test(evals): add the capture classification dataset v1"
```

---

### Task 3: 指標の計算

**Files:**

- Create: `apps/api/src/hibi/evals/metrics.py`
- Test: `apps/api/tests/test_eval_metrics.py`

**Interfaces:**

- Produces:
  - `LabelScores(precision: float, recall: float, f1: float, support: int)`
  - `accuracy(expected: Sequence[str], predicted: Sequence[str]) -> float`
  - `per_label_scores(expected, predicted, *, labels: Sequence[str]) -> dict[str, LabelScores]`
  - `macro_f1(scores: Mapping[str, LabelScores]) -> float` — `support > 0` の label だけを平均する
  - `confusion_matrix(expected, predicted, *, labels: Sequence[str]) -> dict[str, dict[str, int]]` — 行は正解、列は予測。`labels` に無い予測(`"error"` など)も列に加える
  - `binary_scores(expected: Sequence[bool], predicted: Sequence[bool]) -> LabelScores`
  - `CalibrationBin(lower: float, upper: float, count: int, accuracy: float | None)`
  - `calibration_bins(confidences: Sequence[float], correct: Sequence[bool], *, bin_count: int = 10) -> list[CalibrationBin]`
  - `percentile(values: Sequence[float], q: float) -> float | None` — nearest-rank 法。空なら None
  - `recall_at_k(ranked: Sequence[str], relevant: AbstractSet[str], k: int) -> float`
  - `reciprocal_rank(ranked, relevant) -> float`
  - `ndcg_at_k(ranked, relevant, k: int) -> float` — 関連は 2 値、割引は `1 / log2(rank + 1)`
  - `mean_and_std(values: Sequence[float]) -> tuple[float, float]` — std は標本標準偏差。1 件なら 0.0

- [ ] **Step 1: Write the failing tests** in `tests/test_eval_metrics.py`

```python
_EXPECTED = ["shopping", "shopping", "note", "chat"]
_PREDICTED = ["shopping", "note", "note", "chat"]
_LABELS = ["shopping", "reminder", "expense", "note", "chat"]

def test_accuracy() -> None:
    assert accuracy(_EXPECTED, _PREDICTED) == 0.75
    assert accuracy([], []) == 0.0

def test_per_label_scores_and_macro_f1() -> None:
    scores = per_label_scores(_EXPECTED, _PREDICTED, labels=_LABELS)
    assert scores["shopping"] == LabelScores(precision=1.0, recall=0.5, f1=pytest.approx(2 / 3), support=2)
    assert scores["note"].precision == 0.5 and scores["note"].recall == 1.0
    assert scores["reminder"] == LabelScores(precision=0.0, recall=0.0, f1=0.0, support=0)
    assert macro_f1(scores) == pytest.approx((2 / 3 + 2 / 3 + 1.0) / 3)

def test_confusion_matrix_keeps_unknown_predictions() -> None:
    matrix = confusion_matrix(["shopping", "note"], ["note", "error"], labels=_LABELS)
    assert matrix["shopping"]["note"] == 1
    assert matrix["note"]["error"] == 1

def test_binary_scores() -> None:
    assert binary_scores([True, True, False], [True, False, True]) == LabelScores(
        precision=0.5, recall=0.5, f1=0.5, support=2
    )

def test_calibration_bins_put_one_in_the_last_bin() -> None:
    bins = calibration_bins([0.95, 0.72, 0.65, 1.0], [True, False, True, True])
    assert len(bins) == 10
    assert (bins[9].count, bins[9].accuracy) == (2, 1.0)
    assert (bins[7].count, bins[7].accuracy) == (1, 0.0)
    assert (bins[6].count, bins[6].accuracy) == (1, 1.0)
    assert (bins[0].count, bins[0].accuracy) == (0, None)
    assert calibration_bins([0.7], [True])[7].count == 1  # 浮動小数の 0.7 * 10 で区間がずれない

def test_percentile_uses_nearest_rank() -> None:
    assert percentile([40, 10, 30, 20], 50) == 20
    assert percentile([40, 10, 30, 20], 95) == 40
    assert percentile([], 50) is None

def test_retrieval_metrics() -> None:
    ranked, relevant = ["d3", "d1", "d2"], {"d1", "d2"}
    assert recall_at_k(ranked, relevant, 1) == 0.0
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert recall_at_k(ranked, relevant, 3) == 1.0
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert reciprocal_rank(["d9"], relevant) == 0.0
    assert ndcg_at_k(ranked, relevant, 3) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    )

def test_mean_and_std() -> None:
    assert mean_and_std([0.8]) == (0.8, 0.0)
    assert mean_and_std([0.7, 0.9]) == (pytest.approx(0.8), pytest.approx(0.14142, abs=1e-5))
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_metrics.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.evals.metrics`)

- [ ] **Step 3: Implement**

**evals**(`evals/metrics.py`、純粋関数)

- 割り算の分母が 0 のときは 0.0 を返す(precision、recall、f1、accuracy、recall の relevant が空)
- `calibration_bins`: 区間の番号は `min(int(Decimal(str(c)) * bin_count), bin_count - 1)`。浮動小数のまま掛けない
- `percentile`: 昇順に並べ、`ceil(q / 100 * n)` 番目(1 始まり)
- `mean_and_std`: `statistics.mean` と `statistics.stdev`

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_metrics.py -v`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/evals/metrics.py apps/api/tests/test_eval_metrics.py
git commit -m "feat(evals): add classification and retrieval metrics"
```

---

### Task 4: 分類の run、レポート、CLI

**Files:**

- Create: `apps/api/src/hibi/ai/usage.py`、`apps/api/src/hibi/evals/report.py`、`apps/api/src/hibi/evals/classification.py`、`apps/api/src/hibi/evals/__main__.py`、`docs/ai/reports/.gitkeep`
- Modify: `justfile`
- Test: `apps/api/tests/test_eval_report.py`、`apps/api/tests/test_eval_classification.py`

**Interfaces:**

- Consumes: Task 1 の dataset、Task 3 の指標、`hibi.ai.classification.CaptureClassifier`、`ClassificationTimeoutError`、`CAPTURE_QUESTION_VERSION`、`hibi.modules.captures.policies.normalize_classification`、`decide_capture_route`、`CAPTURE_ROUTE_CLARIFY`、`CAPTURE_CATEGORIES`
- Produces:
  - `hibi.ai.usage.LlmUsage`(可変の dataclass): `calls: int = 0`、`input_tokens: int | None = 0`、`output_tokens: int | None = 0`、`invalid_outputs: int = 0`、`add(*, input_tokens: int | None, output_tokens: int | None) -> None`(片方でも None が来たら、その項目を以後 None にする。「不明」を 0 と混ぜない)、`record_invalid() -> None`
  - `DatasetRef(path: str, sha256: str)` — path はリポジトリからの相対パス
  - `RunMetadata(suite: str, label: str, started_at: datetime, git_sha: str, git_dirty: bool, datasets: tuple[DatasetRef, ...], implementation: str, model: str | None, base_url_host: str | None, prompt_version: str | None, temperature: float | None, repeats: int)`
  - `base_url_host(base_url: str | None) -> str | None` — `urlsplit(...).hostname` と port だけ
  - `git_state(repo_root: Path) -> tuple[str, bool]` — `git rev-parse HEAD` と `git status --porcelain` が空でないか
  - `report_paths(reports_dir: Path, *, suite: str, label: str, started_at: datetime) -> tuple[Path, Path]` — 既にあれば `-2`、`-3` を付ける
  - `write_report(*, metadata: RunMetadata, metrics: Mapping[str, object], cases: Sequence[Mapping[str, object]], markdown: str, reports_dir: Path) -> tuple[Path, Path]` — JSON は `{"metadata", "metrics", "cases"}`
  - `render_metadata_markdown(metadata: RunMetadata) -> str`
  - `ClassificationPrediction(case_id: str, repeat: int, category: str, confidence: float | None, route: str | None, latency_ms: float, error: str | None)` — 失敗は `category="error"`、`error="timeout"`
  - `ClassificationRunResult(predictions: tuple[ClassificationPrediction, ...], metrics: dict[str, object])`
  - `async run_classification(cases: Sequence[ClassificationCase], classifier: CaptureClassifier, *, repeats: int = 1, concurrency: int = 4, usage: LlmUsage | None = None, clock: Callable[[], float] = time.perf_counter) -> ClassificationRunResult`
  - `render_classification_markdown(metadata: RunMetadata, result: ClassificationRunResult) -> str`
  - `hibi.evals.__main__.main(argv: Sequence[str] | None = None) -> int` — 0: 完了、2: 引数・評価データ・キーの不備、130: 中断

- [ ] **Step 1: Write the failing tests**

`tests/test_eval_report.py`

```python
def test_base_url_host_drops_credentials_and_path() -> None:
    assert base_url_host("https://user:secret@api.example.com/v1") == "api.example.com"
    assert base_url_host("http://localhost:8080/v1") == "localhost:8080"
    assert base_url_host(None) is None

def test_report_paths_do_not_overwrite_an_earlier_run(tmp_path) -> None:
    started = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)
    first_md, first_json = report_paths(tmp_path, suite="classification", label="jev", started_at=started)
    assert first_md.name == "2026-12-01-classification-jev.md"
    first_md.write_text("x")
    second_md, second_json = report_paths(tmp_path, suite="classification", label="jev", started_at=started)
    assert second_md.name == "2026-12-01-classification-jev-2.md"
    assert second_json.name == "2026-12-01-classification-jev-2.json"

def test_write_report_records_the_run_metadata(tmp_path) -> None: ...
    # JSON の metadata に git_sha、git_dirty、datasets[0].sha256、model、base_url_host が入り、
    # Markdown と JSON のどちらにも "secret" が出ない

def test_llm_usage_keeps_unknown_tokens_unknown() -> None:
    usage = LlmUsage()
    usage.add(input_tokens=10, output_tokens=5)
    usage.add(input_tokens=None, output_tokens=7)
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (2, None, 12)
```

`tests/test_eval_classification.py`(分類器は test の中の stub。`text -> (category, confidence)` の dict を引き、`"TIMEOUT"` なら `ClassificationTimeoutError` を投げる。clock は呼ぶたびに 0.01 秒進む stub)

```python
async def test_run_classification_scores_routes_and_failures() -> None: ...
    # 4 ケース(shouldClarify は 3 件目だけ true):
    #   1. 正しい category、confidence 0.9
    #   2. 違う category、confidence 0.9
    #   3. 正しい category、confidence 0.5 → route は clarify
    #   4. TIMEOUT
    # metrics["accuracy"] == 0.5(失敗は不正解に数える)、metrics["failures"] == 1
    # clarify は失敗を除いた 3 件で計算し、precision == 1.0、recall == 1.0
    # predictions の順は cases の順。失敗の行は category == "error"、error == "timeout"

async def test_disputed_cases_are_left_out_of_the_metrics() -> None: ...
    # tags に "disputed" のケースは metrics の件数に入らず、metrics["disputed"] == 1

async def test_repeats_report_mean_and_std() -> None: ...
    # repeats=2 で predictions は 2 倍、metrics["accuracy_mean"] と ["accuracy_std"] がある

async def test_run_classification_limits_concurrency() -> None: ...
    # 同時実行数を数える stub。concurrency=2 なら最大 2

def test_main_writes_a_report_with_the_fake_classifier(tmp_path) -> None: ...
    # main(["classification", "--classifier", "fake", "--dataset", <2 行の tmp dataset>,
    #       "--reports-dir", str(tmp_path)]) == 0、md と json が 1 つずつできる

def test_main_stops_before_calling_on_a_broken_dataset(tmp_path, monkeypatch) -> None: ...
    # 壊れた dataset で 2 を返し、stub の分類器は呼ばれず、レポートも無い

def test_main_writes_no_report_when_interrupted(tmp_path, monkeypatch) -> None: ...
    # 分類器が KeyboardInterrupt を投げる → 130、tmp_path は空

def test_main_requires_a_jev_key(tmp_path, monkeypatch) -> None: ...
    # HIBI_JEV_API_KEY が空で --classifier jev → 2、何も呼ばない
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_report.py apps/api/tests/test_eval_classification.py -v`
Expected: FAIL(`ModuleNotFoundError`)

- [ ] **Step 3: Implement**

**ai**(`ai/usage.py`)

- `LlmUsage`: 上の Interfaces のとおり。`add` は `calls` を 1 増やす

**evals**(`evals/report.py`)

- `git_state`: `subprocess.run(["git", ...], cwd=repo_root, check=True, capture_output=True, text=True)`
- `write_report`: 親の directory を作り、JSON は `ensure_ascii=False, indent=2`、datetime は ISO 8601
- `render_metadata_markdown`: 英語の見出し `## Run` の下に、metadata の表。`git_dirty` が true なら、その行に `uncommitted changes` と書く

**evals**(`evals/classification.py`)

- `run_classification`: `asyncio.Semaphore(concurrency)` で絞り、`asyncio.gather` で全ケース × repeats を流す。各ケースで `classify_capture(raw_text, question_version=CAPTURE_QUESTION_VERSION)` → `normalize_classification` → `decide_capture_route`。`ClassificationTimeoutError` だけを捕まえて失敗にし、他の例外は上へ流す
- 集計: `disputed` を除いたケースで、accuracy、per-label、macro-F1、混同行列(`labels` は `CAPTURE_CATEGORIES` を `shopping, reminder, expense, note, chat` の順)、clarify の `binary_scores`(失敗を除く)、calibration(失敗を除く)、tags ごとの accuracy、latency の p50 と p95、failures、disputed、`usage`(あれば `asdict`)。repeats が 2 以上なら accuracy、macro-F1、clarify の F1 を repeat ごとに出し、`_mean` と `_std` を付ける。表の詳細は全 repeat を合わせた予測で作る
- `render_classification_markdown`: 英語。`render_metadata_markdown` のあとに `## Summary`、`## Per category`、`## Confusion matrix`、`## Clarification`、`## Calibration`、`## By tag`、`## Latency and cost`

**cli**(`evals/__main__.py`)

- `argparse` の subcommand `classification`: `--classifier {fake,jev,llm}`(必須)、`--base-url`、`--model`、`--label`(既定は classifier の名前)、`--repeats`(1)、`--max-cases`、`--concurrency`(4)、`--dataset`(既定 `CLASSIFICATION_DATASET`)、`--reports-dir`(既定 `REPORTS_DIR`)
- 順番: 評価データを読む → キーを確かめる → 呼び出す回数を表示 → `asyncio.run` → レポートを書く → 2 つのパスを表示。`DatasetError` とキーの不足は stderr に出して 2。`KeyboardInterrupt` は 130 で、何も書かない
- `--classifier llm` は Task 5 で繋ぐ。この Task では「Task 5 で対応」として 2 を返す

**justfile**

```make
eval-classification *args:
    cd apps/api && uv run python -m hibi.evals classification {{args}}
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_report.py apps/api/tests/test_eval_classification.py -v`、`ruff check`、`ruff format --check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: baseline を取る**

Run: `just eval-classification --classifier fake` と、`HIBI_JEV_API_KEY` を設定して `just eval-classification --classifier jev`
Expected: `docs/ai/reports/` に、`classification-fake` と `classification-jev` の md と json ができる。fake は、評価データの多くを `chat 0.5` にするので、指標が低いのが正しい(仕組みの確認用)

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/hibi/ai/usage.py apps/api/src/hibi/evals apps/api/tests/test_eval_report.py apps/api/tests/test_eval_classification.py justfile docs/ai/reports
git commit -m "feat(evals): run the classification evaluation and write reports"
```

---

### Task 5: LLM の分類器

**Files:**

- Create: `apps/api/src/hibi/ai/llm_classifier.py`
- Modify: `apps/api/src/hibi/evals/__main__.py`
- Test: `apps/api/tests/test_llm_classifier.py`、`apps/api/tests/test_eval_classification.py`(1 件足す)

**Interfaces:**

- Consumes: `Classification`、`ClassificationTimeoutError`、`hibi.ai.metrics.record_llm_call`、Task 4 の `LlmUsage`
- Produces:
  - `CAPTURE_LLM_CLASSIFY_PROMPT_VERSION = "capture-llm-classify-v1"`
  - `CompletionResult(content: str, input_tokens: int | None, output_tokens: int | None)`
  - `ClassificationModelClient`(Protocol): `async complete_json(self, *, text: str) -> CompletionResult`
  - `SdkClassificationClient(*, base_url: str | None = None, model: str | None = None, api_key: str | None = None)` — None の項目は設定値(`open_ai_base_url`、`open_ai_model`、`open_ai_api_key`)を使う
  - `LlmCaptureClassifier(client: ClassificationModelClient | None = None, *, usage: LlmUsage | None = None)`、`async classify_capture(self, text: str, *, question_version: str) -> Classification`

- [ ] **Step 1: Write the failing tests** in `tests/test_llm_classifier.py`(偽の client。例外の作り方は `test_llm_review_summary.py` の `_Timeout` などと同じ)

```python
async def test_reads_a_valid_json_output() -> None: ...
    # '{"category":"shopping","confidence":0.82,"urgency":0.3}' →
    # Classification(category="shopping", confidence=Decimal("0.82"), urgency_score=0.3,
    #                question_version="capture-classify-v1")

async def test_invalid_output_becomes_unknown_and_is_counted() -> None: ...
    # "not json"、'{"category":"shopping"}'、confidence 1.5 の 3 通り →
    # category "unknown"、confidence Decimal("0")、usage.invalid_outputs が 1 ずつ増える

async def test_provider_failures_become_classification_timeout() -> None: ...
    # APITimeoutError、APIConnectionError、RateLimitError、InternalServerError → ClassificationTimeoutError

async def test_records_tokens_and_llm_calls() -> None: ...
    # CompletionResult(input_tokens=120, output_tokens=15) → usage が (1, 120, 15)、llm_call_count() == 1

async def test_missing_usage_from_a_local_server_does_not_crash() -> None: ...
    # input_tokens=None, output_tokens=None → 正しい Classification、usage.input_tokens is None

def test_sdk_client_sends_temperature_zero_and_json_mode(monkeypatch) -> None: ...
    # AsyncOpenAI を偽物に替え、create の kwargs に temperature=0、
    # response_format={"type": "json_object"}、引数の model が入る。system の文に "JSON" が入る
```

`tests/test_eval_classification.py` に足す:

```python
def test_main_allows_a_local_llm_without_a_key(tmp_path, monkeypatch) -> None: ...
    # --classifier llm --base-url http://localhost:8080/v1 --model m で、HIBI_OPEN_AI_API_KEY が空でも 2 にならない
    # (SdkClassificationClient を偽物に替える)。--base-url も key も無ければ 2
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_llm_classifier.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.ai.llm_classifier`)

- [ ] **Step 3: Implement**

**ai**(`ai/llm_classifier.py`)

- system の文(この文で版を固定する。変えたら版を上げる):

```text
次の一文を、許可された category のどれか 1 つに分類する。
shopping: 買う、注文する、在庫を補う
reminder: 時刻や日付を伴う予定、想起
expense: 金額を伴う支出の記録
note: 後で読む、保管する情報
chat: 会話、感想、上のどれにも決まらない雑談
confidence は、選んだ category が正しい確率の自己評価を 0 から 1 で書く。
urgency は、この一文の緊急度を 0 から 1 で書く。
返答は {"category":"...","confidence":0.0,"urgency":0.0} の形の JSON だけにする。
```

- `SdkClassificationClient.complete_json`: `AsyncOpenAI(api_key=..., base_url=..., timeout=open_ai_timeout_seconds, max_retries=0)`。`temperature=0`、`response_format={"type": "json_object"}`。`completion.usage` が無ければトークンは None。4 つの例外を `ClassificationTimeoutError` にする。api_key が空のときは `"local"` を渡す(手元のサーバーはキーを見ない)
- `LlmCaptureClassifier.classify_capture`: `record_llm_call()` → `complete_json` → usage に足す → Pydantic(`category: str`、`confidence: float = Field(ge=0, le=1)`、`urgency: float = Field(ge=0, le=1)`、`extra="ignore"`)で読む。`json.JSONDecodeError` と `ValidationError` は `record_invalid()` して `category="unknown"`、`confidence=Decimal("0")`、`urgency_score=0.0`。confidence は `Decimal(str(value))`
- `factory.py` には繋がない

**cli**(`evals/__main__.py`)

- `--classifier llm`: `--base-url` も `HIBI_OPEN_AI_API_KEY` も無ければ 2。`LlmUsage` を作って分類器と `run_classification` の両方に渡す。metadata の `model` は `--model` か設定値、`prompt_version` は `CAPTURE_LLM_CLASSIFY_PROMPT_VERSION`、`temperature` は 0.0。`--concurrency` を指定しなければ、`--base-url` があるときは 1

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_llm_classifier.py apps/api/tests/test_eval_classification.py -v`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: 商用の LLM と、手元のモデルで run する**

1. 商用: `just eval-classification --classifier llm --label openai-<model>`(設定値の model)
2. 手元: `uv tool run --from mlx-lm mlx_lm.server --model mlx-community/Qwen2.5-7B-Instruct-4bit --port 8080` を別の端末で起動し、`just eval-classification --classifier llm --base-url http://localhost:8080/v1 --model mlx-community/Qwen2.5-7B-Instruct-4bit --label local-qwen2.5-7b`。最初に `--max-cases 5` で 1 件あたりの時間を確かめる

Expected: 2 つのレポートができる。手元のモデルの usage が「unknown」でも、指標は出る

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/hibi/ai/llm_classifier.py apps/api/src/hibi/evals/__main__.py apps/api/tests/test_llm_classifier.py apps/api/tests/test_eval_classification.py docs/ai/reports
git commit -m "feat(ai): add an LLM capture classifier for evaluation"
```

---

### Task 6: hybrid 検索

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/search.py`、`types.py`、`service.py`、`router.py`、`packages/api-client/src/generated/*`(`just openapi`)
- Test: `apps/api/tests/test_capture_search.py`、`apps/api/tests/test_capture_search_service.py`、`apps/api/tests/test_capture_api.py`

**Interfaces:**

- Consumes: 既存の `rank_capture_by_keyword`、`rank_captures_by_semantic`、`SearchDocument`、`TextEmbedder`
- Produces:
  - `RRF_K = 60`
  - `async rank_captures_by_hybrid(documents: Sequence[SearchDocument], *, user_id: UUID, query: str, embedder: TextEmbedder) -> list[UUID]`
  - `CAPTURE_SEARCH_MODE_HYBRID = "hybrid"`、`CaptureSearchMode = Literal["keyword", "semantic", "hybrid"]`

- [ ] **Step 1: Write the failing tests**

`tests/test_capture_search.py`(質問の embedding は、test の中の stub embedder が dict で返す。文書の embedding は `_document(..., embedding=Embedding(...))` で直接持たせる)

```python
async def test_hybrid_puts_a_document_found_by_both_methods_first() -> None: ...
    # 質問「牛乳」、stub の質問ベクトル (1, 0)
    # A「牛乳を買う」(0.6, 0.8): keyword 1 位、semantic 2 位
    # B「ミルクを買う」(1, 0): semantic 1 位だけ
    # C「パンを買う」(0, 1): どちらにも出ない(類似度 0)
    # → [A, B]。A = 1/61 + 1/62 > B = 1/61

async def test_hybrid_breaks_ties_by_capture_id() -> None: ...
    # keyword だけの 1 位 UUID(int=5) と、semantic だけの 1 位 UUID(int=3) → [UUID(int=3), UUID(int=5)]

async def test_hybrid_ignores_other_users_and_unfinished_captures() -> None: ...
```

`tests/test_capture_search_service.py`: `mode="hybrid"` で hybrid の順に Capture が返る 1 件。`tests/test_capture_api.py`: `GET /api/v1/captures/search?q=牛乳&mode=hybrid` が 200、`mode=other` が 422 の 2 件。

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_search.py apps/api/tests/test_capture_search_service.py apps/api/tests/test_capture_api.py -v -k hybrid`
Expected: FAIL(`ImportError: rank_captures_by_hybrid`)

- [ ] **Step 3: Implement**

**domain**(`modules/captures/search.py`)

- `rank_captures_by_hybrid`: 2 つの既存関数を呼び、それぞれの順位 `r`(1 始まり)から `1 / (RRF_K + r)` を足し合わせる。`(-score, capture_id)` で並べる。他人の行、未完了の行、類似度 0 の除外は既存関数に任せる
- docstring に、RRF の式と、片方だけに出た文書も残る理由を書く

**types / service / router**

- `types.py`: `CAPTURE_SEARCH_MODE_HYBRID`、`CaptureSearchMode` に `"hybrid"`。`SearchCapturesQuery` の docstring も 3 つにする
- `service.py`: `search_captures` の分岐に hybrid を足す
- `router.py`: 既定は `keyword` のまま。docstring に「mode=hybrid は両方の順位をまとめる」と足す。`just openapi` で再生成する

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests -v -k "search or hybrid"`、`ruff check`、`ty check apps/api/src`、`just openapi`、`corepack pnpm typecheck`
Expected: PASS。生成物の差分は `mode` の enum に `hybrid` が増えるだけ

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/modules/captures apps/api/tests packages/api-client/src/generated
git commit -m "feat(search): add hybrid search with reciprocal rank fusion"
```

---

### Task 7: 検索の評価データと run

**Files:**

- Create: `docs/ai/evals/capture-search-corpus-v1.jsonl`、`docs/ai/evals/capture-search-queries-v1.jsonl`、`apps/api/src/hibi/evals/search.py`
- Modify: `apps/api/src/hibi/ai/provider_embedder.py`、`apps/api/src/hibi/evals/__main__.py`、`justfile`
- Test: `apps/api/tests/test_eval_search.py`、`apps/api/tests/test_provider_embedder.py`、`apps/api/tests/test_eval_datasets.py`

**Interfaces:**

- Consumes: Task 1 の `load_search_dataset`、Task 3 の指標、Task 4 の report、Task 6 の `rank_captures_by_hybrid` と既存の 2 関数
- Produces:
  - `ProviderTextEmbedder(client: EmbeddingModelClient | None = None, *, dimensions: int = CAPTURE_EMBED_DIMENSIONS)`
  - `SEARCH_MODES = ("keyword", "semantic", "hybrid")`
  - `QueryResult(query_id: str, mode: str, ranked_doc_ids: tuple[str, ...], latency_ms: float)`
  - `SearchRunResult(results: tuple[QueryResult, ...], metrics: dict[str, object])`
  - `async run_search(corpus: Sequence[SearchDocumentCase], queries: Sequence[SearchQueryCase], *, embedder: TextEmbedder, clock: Callable[[], float] = time.perf_counter) -> SearchRunResult`
  - `render_search_markdown(metadata: RunMetadata, result: SearchRunResult) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_provider_embedder.py` に足す:

```python
async def test_embedder_uses_the_requested_dimensions() -> None: ...
    # dimensions=256 → client に 256 が渡り、Embedding.dimensions == 256。長さが違えば EmbeddingProviderError
```

`tests/test_eval_search.py`(stub embedder、文書 4 件、質問 2 件、clock の stub)

```python
async def test_run_search_scores_every_mode() -> None: ...
    # metrics["keyword"]、["semantic"]、["hybrid"] に recall_at_5、recall_at_10、mrr、ndcg_at_5、
    # latency_p50_ms、latency_p95_ms、by_tag がある。keyword の値は手で計算した値と一致

async def test_run_search_embeds_the_corpus_once() -> None: ...
    # stub embedder の呼び出し = 文書 4 件 + 質問の embedding(semantic と hybrid で質問ごとに 1 回ずつ)

def test_main_writes_a_search_report_with_the_fake_embedder(tmp_path) -> None: ...
```

`tests/test_eval_datasets.py` に足す:

```python
def test_the_committed_search_dataset_is_valid() -> None:
    corpus, queries = load_search_dataset(SEARCH_CORPUS, SEARCH_QUERIES)
    assert len(corpus.cases) >= 60 and len(queries.cases) >= 30
    assert {"exact", "synonym", "paraphrase", "notation"} <= {t for q in queries.cases for t in q.tags}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_search.py apps/api/tests/test_provider_embedder.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.evals.search`、`TypeError: dimensions`)

- [ ] **Step 3: 評価データの案を Claude が作り、ユーザーが確定する**

- 文書 60〜70 件(5 つの category にまたがる、実際に記録しそうな本文)、ID は `doc-001` から
- 質問 30〜35 件。`exact`、`synonym`(牛乳とミルク)、`paraphrase`(意味だけ近い)、`notation`(かなとカナ、全角と半角)をそれぞれ 6 件以上

- [ ] **Step 4: Implement**

**ai**(`ai/provider_embedder.py`)

- `dimensions` を受け、client への引数、長さの確認、`Embedding.dimensions` に使う。既定は `CAPTURE_EMBED_DIMENSIONS` なので、本番の動きは変わらない

**evals**(`evals/search.py`)

- 文書は `SearchDocument(capture_id=uuid5(NAMESPACE_URL, doc_id), user_id=UUID(int=1), status=CAPTURE_STATUS_COMPLETED, text=..., embedding=...)` にする。embedding は run の最初に 1 件ずつ作る。UUID から doc_id へ戻す dict を持つ
- 質問ごと、mode ごとに順位付けの関数を呼び、`clock` で latency を測る(semantic と hybrid は質問の embedding を含む)
- mode ごとに Recall@5、Recall@10、MRR、nDCG@5、tags ごとの Recall@5、latency の p50 と p95。`disputed` の質問は外す
- `render_search_markdown`: 英語。`## Run`、`## Comparison`(mode を行にした 1 つの表)、`## By tag`、`## Latency`

**cli**(`evals/__main__.py`)

- subcommand `search`: `--embedder {fake,provider}`(必須)、`--dimensions`(provider だけ。既定 8)、`--label`(既定 `<embedder>-<dimensions>d`)、`--corpus`、`--queries`、`--reports-dir`。`provider` は `HIBI_OPEN_AI_EMBEDDING_API_KEY` が無ければ 2

**justfile**

```make
eval-search *args:
    cd apps/api && uv run python -m hibi.evals search {{args}}
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_eval_search.py apps/api/tests/test_provider_embedder.py apps/api/tests/test_eval_datasets.py -v`、`ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 6: run する**

Run: `just eval-search --embedder fake`、`just eval-search --embedder provider`(本番と同じ 8 次元)、`just eval-search --embedder provider --dimensions 256`
Expected: 3 つのレポート。8 次元と 256 次元の semantic の差が、本番の次元を見直すかの材料になる

- [ ] **Step 7: Commit**

```bash
git add docs/ai/evals/capture-search-*.jsonl apps/api/src/hibi/evals/search.py apps/api/src/hibi/evals/__main__.py apps/api/src/hibi/ai/provider_embedder.py apps/api/tests justfile docs/ai/reports
git commit -m "feat(evals): compare keyword, semantic and hybrid search"
```

---

### Task 8: 判断の記録と全ゲート

**Files:**

- Modify: `docs/architecture/30-week10-5-evaluation-and-hybrid-search.md`、`docs/architecture/11-implementation-schedule.md`

- [ ] **Step 1: 結果を spec の末尾に記録する**

`## 結果と判断` の節を足す。

- 分類: Jev、商用の LLM、手元のモデルの accuracy、macro-F1、clarify の F1、p50 latency、トークン数の表と、レポートへのリンク。calibration から見て、閾値 0.70 が妥当か
- 検索: 3 方式の Recall@5、MRR、p50 の表。spec の規則(hybrid の MRR と Recall@5 が、どちらも 2 方式以上)で、既定を hybrid に変えるかの結論。変える場合は、画面の整理の作業で行うと書く
- embedding の次元: 8 次元と 256 次元の semantic の差と、本番の次元を見直すかの提案(見直すなら、migration を伴う別の作業)

- [ ] **Step 2: Run every gate**

Run: `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`、`ruff check`(同じ範囲)、`ty check apps/api/src`、`uv run --project apps/api pytest apps/api/tests`、`corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`、`just openapi` で差分が出ない
Expected: すべて GREEN(`test_auth_supabase_local.py` の 2 件は既存の失敗)。build のあと `git checkout apps/web/next-env.d.ts`

- [ ] **Step 3: Commit**

```bash
git add docs/architecture/30-week10-5-evaluation-and-hybrid-search.md docs/architecture/11-implementation-schedule.md
git commit -m "docs: record the week 10.5 evaluation results"
```

---

## 判断メモ

- **評価データを新しいファイルにする理由:** `capture-route-v1.jsonl` は、fake の分類器が本文から答えを引く表で、Week 5 からのテストが依存している。評価のために書き換えると、fake の動きとテストが変わる。
- **失敗を不正解に数える理由:** 利用者から見ると、timeout も分類の失敗も、同じく「正しく仕分けられなかった」になる。一方、clarify と calibration は、モデルの判断の質を見る指標なので、判断が無い失敗は除く。
- **手元のモデルではキーを要らなくする理由:** `mlx_lm.server` や `llama-server` は、キーを確かめない。`--base-url` を指定したときだけ、キーが空でも動かす。
- **トークン数の「不明」を 0 にしない理由:** 手元のサーバーは usage を返さないことがある。0 と書くと、費用が 0 だと誤読される。
- **embedding の次元を、評価でだけ変えられるようにした理由(spec への追記):** 本番の `vector(8)` は、Week 8 で fake と揃えるために決めた値で、実際のモデルの品質には小さい。DB を変えずに、まず差を測る。
- **要確認(spec で決めた前提):** 評価データの件数(60 件、文書 60 件、質問 30 件)、hybrid を既定にする規則、レポートを英語にすること。
