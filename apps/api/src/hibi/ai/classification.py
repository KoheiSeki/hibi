from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

CAPTURE_QUESTION_VERSION = "capture-classify-v1"

CLARIFICATION_FALLBACK_TEXT = "もう少し具体的に教えてください。"
CLARIFICATION_TEXT_MAX_LENGTH = 500


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    confidence: Decimal
    urgency_score: float
    question_version: str


@dataclass
class ClassificationTimeoutError(Exception):
    pass


@dataclass
class ClarificationProviderError(Exception):
    pass


class CaptureClassifier(Protocol):
    async def classify_capture(
        self, text: str, *, question_version: str
    ) -> Classification: ...


class ClarificationGenerator(Protocol):
    async def generate_clarification(self, text: str, *, category: str) -> str: ...


def normalize_clarification_text(text: str) -> str:
    if text.strip() == "" or len(text) > CLARIFICATION_TEXT_MAX_LENGTH:
        return CLARIFICATION_FALLBACK_TEXT
    return text
