import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from hibi.evals.datasets import (
    ClassificationCase,
    DatasetError,
    SearchDocumentCase,
    SearchQueryCase,
    load_classification_cases,
    load_search_dataset,
)


def _classification_row(case_id: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "caseId": case_id,
        "rawText": "牛乳を買う",
        "expectedCategory": "shopping",
        "shouldClarify": False,
        "tags": ["basic"],
    }
    row.update(overrides)
    return row


def _write_jsonl(path: Path, rows: list[dict[str, Any] | str]) -> Path:
    lines = [row if isinstance(row, str) else json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_loads_classification_cases_and_hashes_the_file(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [
            _classification_row("cls-001"),
            "",
            _classification_row(
                "cls-002",
                rawText="あれやっといて",
                expectedCategory="chat",
                shouldClarify=True,
                tags=["ambiguous", "colloquial"],
            ),
        ],
    )

    dataset = load_classification_cases(path)

    assert dataset.path == path
    assert dataset.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert dataset.cases == (
        ClassificationCase(
            case_id="cls-001",
            raw_text="牛乳を買う",
            expected_category="shopping",
            should_clarify=False,
            tags=("basic",),
        ),
        ClassificationCase(
            case_id="cls-002",
            raw_text="あれやっといて",
            expected_category="chat",
            should_clarify=True,
            tags=("ambiguous", "colloquial"),
        ),
    )


def test_rejects_an_unknown_category_with_the_line_number(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [
            _classification_row("cls-001"),
            _classification_row("cls-002", expectedCategory="learning"),
        ],
    )

    with pytest.raises(DatasetError) as error:
        load_classification_cases(path)

    assert "classification.jsonl" in str(error.value)
    assert "line 2" in str(error.value)


def test_counts_blank_lines_in_the_line_number(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [
            _classification_row("cls-001"),
            "",
            _classification_row("cls-002", expectedCategory="learning"),
        ],
    )

    with pytest.raises(DatasetError, match="line 3"):
        load_classification_cases(path)


def test_rejects_a_duplicate_case_id(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [_classification_row("cls-001"), _classification_row("cls-001")],
    )

    with pytest.raises(DatasetError) as error:
        load_classification_cases(path)

    assert "line 2" in str(error.value)
    assert "cls-001" in str(error.value)


def test_rejects_a_missing_field_and_invalid_json(tmp_path: Path) -> None:
    missing = _classification_row("cls-002")
    del missing["rawText"]
    missing_path = _write_jsonl(
        tmp_path / "missing.jsonl",
        [_classification_row("cls-001"), missing],
    )
    broken_path = _write_jsonl(
        tmp_path / "broken.jsonl",
        [_classification_row("cls-001"), '{"caseId": "cls-002",'],
    )

    with pytest.raises(DatasetError) as missing_error:
        load_classification_cases(missing_path)
    with pytest.raises(DatasetError) as broken_error:
        load_classification_cases(broken_path)

    assert "missing.jsonl line 2" in str(missing_error.value)
    assert "rawText" in str(missing_error.value)
    assert "broken.jsonl line 2" in str(broken_error.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shouldClarify", "yes"),
        ("tags", "basic"),
        ("tags", [1]),
        ("caseId", 1),
    ],
)
def test_rejects_a_field_of_the_wrong_type(tmp_path: Path, field: str, value: object) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [_classification_row("cls-001", **{field: value})],
    )

    with pytest.raises(DatasetError) as error:
        load_classification_cases(path)

    assert "line 1" in str(error.value)
    assert field in str(error.value)


@pytest.mark.parametrize("raw_text", ["", "   "])
def test_rejects_an_empty_raw_text(tmp_path: Path, raw_text: str) -> None:
    path = _write_jsonl(
        tmp_path / "classification.jsonl",
        [_classification_row("cls-001", rawText=raw_text)],
    )

    with pytest.raises(DatasetError, match="line 1"):
        load_classification_cases(path)


def _write_search_files(tmp_path: Path, queries: list[dict[str, Any] | str]) -> tuple[Path, Path]:
    corpus_path = _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {"docId": "doc-001", "text": "牛乳と卵を買う"},
            {"docId": "doc-002", "text": "歯医者の予約を入れる"},
        ],
    )
    queries_path = _write_jsonl(tmp_path / "queries.jsonl", queries)
    return corpus_path, queries_path


def test_loads_the_search_corpus_and_queries(tmp_path: Path) -> None:
    corpus_path, queries_path = _write_search_files(
        tmp_path,
        [
            {
                "queryId": "q-001",
                "query": "買い物",
                "relevantDocIds": ["doc-001"],
                "tags": ["keyword"],
            },
            {
                "queryId": "q-002",
                "query": "予定",
                "relevantDocIds": ["doc-001", "doc-002"],
                "tags": [],
            },
        ],
    )

    corpus, queries = load_search_dataset(corpus_path, queries_path)

    assert corpus.path == corpus_path
    assert corpus.sha256 == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    assert corpus.cases == (
        SearchDocumentCase(doc_id="doc-001", text="牛乳と卵を買う"),
        SearchDocumentCase(doc_id="doc-002", text="歯医者の予約を入れる"),
    )
    assert queries.sha256 == hashlib.sha256(queries_path.read_bytes()).hexdigest()
    assert queries.cases == (
        SearchQueryCase(
            query_id="q-001",
            query="買い物",
            relevant_doc_ids=frozenset({"doc-001"}),
            tags=("keyword",),
        ),
        SearchQueryCase(
            query_id="q-002",
            query="予定",
            relevant_doc_ids=frozenset({"doc-001", "doc-002"}),
            tags=(),
        ),
    )


def test_rejects_a_query_whose_relevant_doc_is_not_in_the_corpus(tmp_path: Path) -> None:
    corpus_path, queries_path = _write_search_files(
        tmp_path,
        [{"queryId": "q-001", "query": "買い物", "relevantDocIds": ["doc-999"], "tags": []}],
    )

    with pytest.raises(DatasetError) as error:
        load_search_dataset(corpus_path, queries_path)

    assert "queries.jsonl line 1" in str(error.value)
    assert "doc-999" in str(error.value)


def test_rejects_a_query_without_relevant_docs(tmp_path: Path) -> None:
    corpus_path, queries_path = _write_search_files(
        tmp_path,
        [{"queryId": "q-001", "query": "買い物", "relevantDocIds": [], "tags": []}],
    )

    with pytest.raises(DatasetError) as error:
        load_search_dataset(corpus_path, queries_path)

    assert "queries.jsonl line 1" in str(error.value)


def test_rejects_a_duplicate_doc_id_in_the_corpus(tmp_path: Path) -> None:
    corpus_path = _write_jsonl(
        tmp_path / "corpus.jsonl",
        [
            {"docId": "doc-001", "text": "牛乳と卵を買う"},
            {"docId": "doc-001", "text": "歯医者の予約を入れる"},
        ],
    )
    queries_path = _write_jsonl(
        tmp_path / "queries.jsonl",
        [{"queryId": "q-001", "query": "買い物", "relevantDocIds": ["doc-001"], "tags": []}],
    )

    with pytest.raises(DatasetError) as error:
        load_search_dataset(corpus_path, queries_path)

    assert "corpus.jsonl line 2" in str(error.value)
    assert "doc-001" in str(error.value)
