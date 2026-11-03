from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

CAPTURE_QUESTION_VERSION = "capture-classify-v1"


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    confidence: Decimal
    urgency_score: float
    question_version: str


@dataclass
class ClassificationTimeoutError(Exception):
    pass


class CaptureClassifier(Protocol):
    async def classify_capture(
        self, text: str, *, question_version: str
    ) -> Classification: ...
