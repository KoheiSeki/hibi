import json
from decimal import Decimal
from pathlib import Path

import pytest

from hibi.ai.classification import CAPTURE_QUESTION_VERSION, Classification
from hibi.modules.captures.policies import (
    decide_capture_route,
    normalize_classification,
    normalize_urgency_score,
)

_DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "ai" / "evals" / "capture-route-v1.jsonl"
)


def _dataset_cases() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in _DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize("case", _dataset_cases(), ids=lambda case: str(case["rawText"]))
def test_decide_capture_route_matches_dataset(case: dict[str, object]) -> None:
    route = decide_capture_route(
        category=str(case["category"]),
        confidence=Decimal(str(case["confidence"])),
    )

    assert route == case["route"]


def test_dataset_covers_confidence_threshold_boundary() -> None:
    confidences = {Decimal(str(case["confidence"])) for case in _dataset_cases()}

    assert Decimal("0.7") in confidences
    assert Decimal("0.69") in confidences


def _classification(**overrides: object) -> Classification:
    values: dict[str, object] = {
        "category": "shopping",
        "confidence": Decimal("0.9"),
        "urgency_score": 0.5,
        "question_version": CAPTURE_QUESTION_VERSION,
    }
    values.update(overrides)
    return Classification(**values)  # type: ignore[arg-type]


def test_normalize_classification_keeps_a_valid_result() -> None:
    classification = _classification()

    assert normalize_classification(classification) is classification


@pytest.mark.parametrize(
    "overrides",
    [
        {"category": "unknown"},
        {"confidence": Decimal("-0.01")},
        {"confidence": Decimal("1.01")},
        {"question_version": "capture-classify-v0"},
    ],
)
def test_normalize_classification_replaces_invalid_schema(overrides: dict[str, object]) -> None:
    normalized = normalize_classification(_classification(**overrides))

    assert normalized.category == "chat"
    assert normalized.confidence == Decimal("0")
    assert normalized.question_version == CAPTURE_QUESTION_VERSION
    assert normalized.urgency_score == 0.5


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, Decimal("0.00")),
        (0.5, Decimal("0.50")),
        (0.666, Decimal("0.67")),
        (1.0, Decimal("1.00")),
        (-0.1, None),
        (1.1, None),
    ],
)
def test_normalize_urgency_score(score: float, expected: Decimal | None) -> None:
    assert normalize_urgency_score(score) == expected
