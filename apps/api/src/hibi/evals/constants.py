"""評価の道具 (hibi.evals) の中で共有する、パスと tag。

他の file を import しない。datasets、report、classification、search、CLI の
どれからも import できるようにして、循環 import を避けるため。本番のコード (ai、modules) は
この file を import しない。本番が評価の道具に依存しないようにするため。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]
EVALS_DIR = REPO_ROOT / "docs" / "ai" / "evals"
REPORTS_DIR = REPO_ROOT / "docs" / "ai" / "reports"

CLASSIFICATION_DATASET = EVALS_DIR / "capture-classification-v1.jsonl"
SEARCH_CORPUS = EVALS_DIR / "capture-search-corpus-v1.jsonl"
SEARCH_QUERIES = EVALS_DIR / "capture-search-queries-v1.jsonl"

# 正解に迷いがあるケースに付ける tag。このケースは指標の計算から外す
DISPUTED_TAG = "disputed"
