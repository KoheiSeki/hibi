"""Hibi の評価データ (JSONL) を読み込み、検証する。

評価を始める前にデータ全体を検証し、壊れた行が 1 つでもあれば、モデルを呼ぶ前に止める。
JSON の camelCase の項目名と dataclass の snake_case の名前の対応は、この module の中で閉じる。
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from hibi.ai.classification import CAPTURE_CATEGORIES


class DatasetError(Exception):
    """評価データの形式が不正なことを表す。

    メッセージは `"<ファイル名> line <行番号>: <理由>"` の形にする。行番号は 1 始まりで、
    空行も数える。エディタで開いたときの行番号と一致させるため。
    """

    pass


@dataclass(frozen=True)
class ClassificationCase:
    """分類の評価データの 1 ケース。

    Attributes:
        case_id: ケースの ID。ファイルの中で一意。レポートで失敗したケースを指すのに使う。
        raw_text: 利用者が入力したとみなす本文。空白だけの本文は読み込み時に弾く。
        expected_category: 正解の category。`CAPTURE_CATEGORIES` のどれか。
        should_clarify: 確認の質問を返すべきなら True。
        tags: ケースの性質を表す tag。指標を tag ごとに分けて見るのに使う。
    """

    case_id: str
    raw_text: str
    expected_category: str
    should_clarify: bool
    tags: tuple[str, ...]


@dataclass(frozen=True)
class SearchDocumentCase:
    """検索の評価で、検索される側の文書 1 件。

    Attributes:
        doc_id: 文書の ID。corpus の中で一意。query の正解はこの ID で指す。
        text: 文書の本文。
    """

    doc_id: str
    text: str


@dataclass(frozen=True)
class SearchQueryCase:
    """検索の評価の、query 1 件とその正解。

    Attributes:
        query_id: query の ID。ファイルの中で一意。
        query: 検索の文字列。
        relevant_doc_ids: 正解の文書の ID。1 件以上あり、すべて corpus にある。
            順位を付けない 2 値の関連として扱うため、集合で持つ。
        tags: query の性質を表す tag。
    """

    query_id: str
    query: str
    relevant_doc_ids: frozenset[str]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class LoadedDataset[T]:
    """読み込んで検証した評価データと、その出どころ。

    Attributes:
        path: 読み込んだファイルのパス。
        sha256: ファイルのバイト列の SHA-256 (16 進)。レポートに残し、
            どの版のデータで測った結果かを後から確かめられるようにする。
        cases: ファイルに書かれた順のケース。
    """

    path: Path
    sha256: str
    cases: tuple[T, ...]


def load_classification_cases(path: Path) -> LoadedDataset[ClassificationCase]:
    """分類の評価データを読み込み、全行を検証する。

    空行は飛ばす。最初に見つけた不正な行で止め、それ以降の行は読まない。

    Args:
        path: 分類の評価データ (JSONL) のパス。

    Returns:
        検証済みのケースと、ファイルの SHA-256。

    Raises:
        DatasetError: JSON として読めない、必須の項目がない、型が違う、
            category が `CAPTURE_CATEGORIES` に無い、`caseId` が重複する、
            または `rawText` が空白だけの行があるとき。
    """

    sha256, rows = _read_jsonl(path)
    cases: list[ClassificationCase] = []
    seen_ids: set[str] = set()
    for line_number, row in rows:
        where = f"{path.name} line {line_number}"

        case_id = _require_str(row, "caseId", where)
        raw_text = _require_str(row, "rawText", where)
        expected_category = _require_str(row, "expectedCategory", where)
        should_clarify = _require_bool(row, "shouldClarify", where)
        tags = _require_str_list(row, "tags", where)

        if expected_category not in CAPTURE_CATEGORIES:
            raise DatasetError(f"{where}: unknown expectedCategory {expected_category!r}")
        if not raw_text.strip():
            raise DatasetError(f"{where}: rawText is empty")
        if case_id in seen_ids:
            raise DatasetError(f"{where}: duplicate caseId {case_id!r}")
        seen_ids.add(case_id)

        cases.append(
            ClassificationCase(
                case_id=case_id,
                raw_text=raw_text,
                expected_category=expected_category,
                should_clarify=should_clarify,
                tags=tuple(tags),
            )
        )

    return LoadedDataset(path=path, sha256=sha256, cases=tuple(cases))


def load_search_dataset(
    corpus_path: Path, queries_path: Path
) -> tuple[LoadedDataset[SearchDocumentCase], LoadedDataset[SearchQueryCase]]:
    """検索の評価の corpus と query を読み込み、両者の整合を検証する。

    corpus を先に読み、query の正解がすべて corpus にあるかを確かめる。正解が
    corpus に無い query は、Recall や MRR が必ず 0 になり、検索の質と区別できないため弾く。

    Args:
        corpus_path: 検索される文書 (JSONL) のパス。
        queries_path: query と正解 (JSONL) のパス。

    Returns:
        corpus と query の、それぞれの検証済みデータ。

    Raises:
        DatasetError: どちらかのファイルに不正な行があるとき、`docId` か `queryId` が
            重複するとき、`relevantDocIds` が空のとき、または corpus に無い文書を
            正解に含む query があるとき。query の不正は queries のファイル名と行番号で示す。
    """

    corpus = _load_search_corpus(corpus_path)
    doc_ids = frozenset(case.doc_id for case in corpus.cases)
    queries = _load_search_queries(queries_path, doc_ids=doc_ids)
    return corpus, queries


def _read_jsonl(path: Path) -> tuple[str, list[tuple[int, dict[str, object]]]]:
    """JSONL を読み、SHA-256 と、行番号付きの object の列を返す。

    SHA-256 は、デコード前のバイト列から取る。改行コードや BOM の違いも
    別の版として扱うため。

    Args:
        path: 読み込むファイルのパス。

    Returns:
        ファイルの SHA-256 と、空行を除いた `(行番号, object)` の列。
        行番号は 1 始まりで、空行も数える。

    Raises:
        DatasetError: JSON として読めない行、または object でない行があるとき。
    """

    data = path.read_bytes()
    sha256 = hashlib.sha256(data).hexdigest()

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DatasetError(f"{path.name}: not valid UTF-8") from error

    rows: list[tuple[int, dict[str, object]]] = []
    for line_number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        where = f"{path.name} line {line_number}"
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise DatasetError(f"{where}: invalid JSON ({error.msg})") from error
        if not isinstance(value, dict):
            raise DatasetError(f"{where}: expected a JSON object")
        rows.append((line_number, value))
    return sha256, rows


def _require_str(row: dict[str, object], field: str, where: str) -> str:
    """行から文字列の項目を取り出す。

    Args:
        row: JSON の 1 行。
        field: JSON の項目名 (camelCase)。
        where: エラーの位置を表す `"<ファイル名> line <行番号>"`。

    Returns:
        項目の値。

    Raises:
        DatasetError: 項目がない、または文字列でないとき。
    """

    value = _require_field(row, field, where)
    if not isinstance(value, str):
        raise DatasetError(f"{where}: {field} must be a string")
    return value


def _require_bool(row: dict[str, object], field: str, where: str) -> bool:
    """行から真偽値の項目を取り出す。

    `bool(value)` で変換せず、型で確かめる。`"yes"` や `1` を True として
    通すと、データの書き間違いが評価の結果に紛れるため。

    Args:
        row: JSON の 1 行。
        field: JSON の項目名 (camelCase)。
        where: エラーの位置を表す `"<ファイル名> line <行番号>"`。

    Returns:
        項目の値。

    Raises:
        DatasetError: 項目がない、または真偽値でないとき。
    """

    value = _require_field(row, field, where)
    if not isinstance(value, bool):
        raise DatasetError(f"{where}: {field} must be true or false")
    return value


def _require_str_list(row: dict[str, object], field: str, where: str) -> list[str]:
    """行から文字列のリストの項目を取り出す。

    Args:
        row: JSON の 1 行。
        field: JSON の項目名 (camelCase)。
        where: エラーの位置を表す `"<ファイル名> line <行番号>"`。

    Returns:
        項目の値。空のリストも返す。空を許すかは呼び出し側が決める。

    Raises:
        DatasetError: 項目がない、リストでない、または文字列でない要素があるとき。
    """

    value = _require_field(row, field, where)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DatasetError(f"{where}: {field} must be a list of strings")
    return value


def _require_field(row: dict[str, object], field: str, where: str) -> object:
    """行から項目を取り出す。項目が無ければ、項目名を示して止める。"""

    if field not in row:
        raise DatasetError(f"{where}: missing {field}")
    return row[field]


def _load_search_corpus(path: Path) -> LoadedDataset[SearchDocumentCase]:
    """検索の評価の corpus を読み込み、全行を検証する。

    Args:
        path: 検索される文書 (JSONL) のパス。

    Returns:
        検証済みの文書と、ファイルの SHA-256。

    Raises:
        DatasetError: 不正な行があるとき、`docId` が重複するとき、または
            `text` が空白だけのとき。
    """

    sha256, rows = _read_jsonl(path)
    cases: list[SearchDocumentCase] = []
    seen_ids: set[str] = set()
    for line_number, row in rows:
        where = f"{path.name} line {line_number}"

        doc_id = _require_str(row, "docId", where)
        text = _require_str(row, "text", where)

        if doc_id in seen_ids:
            raise DatasetError(f"{where}: duplicate docId {doc_id!r}")
        if not text.strip():
            raise DatasetError(f"{where}: text is empty")
        seen_ids.add(doc_id)

        cases.append(SearchDocumentCase(doc_id=doc_id, text=text))
    return LoadedDataset(path=path, sha256=sha256, cases=tuple(cases))


def _load_search_queries(path: Path, *, doc_ids: frozenset[str]) -> LoadedDataset[SearchQueryCase]:
    """検索の評価の query を読み込み、正解が corpus にあるかを検証する。

    Args:
        path: query と正解 (JSONL) のパス。
        doc_ids: corpus にある文書の ID。正解の ID はすべてこの中にある必要がある。

    Returns:
        検証済みの query と、ファイルの SHA-256。

    Raises:
        DatasetError: 不正な行があるとき、`queryId` が重複するとき、
            `relevantDocIds` が空のとき、または `doc_ids` に無い ID を含むとき。
    """

    sha256, rows = _read_jsonl(path)
    cases: list[SearchQueryCase] = []
    seen_ids: set[str] = set()
    for line_number, row in rows:
        where = f"{path.name} line {line_number}"

        query_id = _require_str(row, "queryId", where)
        query = _require_str(row, "query", where)
        relevant_doc_ids = _require_str_list(row, "relevantDocIds", where)
        tags = _require_str_list(row, "tags", where)

        if query_id in seen_ids:
            raise DatasetError(f"{where}: duplicate queryId {query_id!r}")
        if not query.strip():
            raise DatasetError(f"{where}: query is empty")
        if not relevant_doc_ids:
            raise DatasetError(f"{where}: relevantDocIds is empty")
        missing = sorted(set(relevant_doc_ids) - doc_ids)
        if missing:
            raise DatasetError(f"{where}: relevantDocIds not in the corpus: {', '.join(missing)}")
        seen_ids.add(query_id)

        cases.append(
            SearchQueryCase(
                query_id=query_id,
                query=query,
                relevant_doc_ids=frozenset(relevant_doc_ids),
                tags=tuple(tags),
            )
        )
    return LoadedDataset(path=path, sha256=sha256, cases=tuple(cases))
