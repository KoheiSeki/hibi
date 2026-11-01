import json
from decimal import Decimal
from pathlib import Path

import pytest

from hibi.modules.captures.policies import decide_capture_route

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
