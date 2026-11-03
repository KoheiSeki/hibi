import json
from decimal import Decimal
from pathlib import Path

import pytest

from hibi.ai.classification import CAPTURE_QUESTION_VERSION
from hibi.ai.fake_classifier import FakeCaptureClassifier

_DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "ai" / "evals" / "capture-route-v1.jsonl"
)


def _clear_cases() -> list[dict[str, object]]:
    return [
        case
        for line in _DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and (case := json.loads(line))["confidence"] == 0.9
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _clear_cases(), ids=lambda case: str(case["rawText"]))
async def test_fake_classifier_returns_dataset_category(case: dict[str, object]) -> None:
    result = await FakeCaptureClassifier().classify_capture(
        str(case["rawText"]),
        question_version=CAPTURE_QUESTION_VERSION,
    )

    assert result.category == case["category"]
    assert result.confidence == Decimal(str(case["confidence"]))
    assert result.urgency_score == 0.5
    assert result.question_version == CAPTURE_QUESTION_VERSION
