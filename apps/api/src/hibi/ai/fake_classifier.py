import json
from decimal import Decimal
from pathlib import Path

from hibi.ai.classification import Classification

_DATASET_PATH = (
    Path(__file__).resolve().parents[5] / "docs" / "ai" / "evals" / "capture-route-v1.jsonl"
)


def _load_cases() -> dict[str, tuple[str, Decimal]]:
    cases: dict[str, tuple[str, Decimal]] = {}
    for line in _DATASET_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        case = json.loads(line)
        cases[str(case["rawText"])] = (
            str(case["category"]),
            Decimal(str(case["confidence"])),
        )
    return cases


class FakeCaptureClassifier:
    def classify_capture(self, text: str, *, question_version: str) -> Classification:
        cases = _load_cases()
        matched = cases.get(text)
        if matched is None:
            category, confidence = "chat", Decimal("0.5")
        else:
            category, confidence = matched
        return Classification(
            category=category,
            confidence=confidence,
            urgency_score=0.5,
            question_version=question_version,
        )
