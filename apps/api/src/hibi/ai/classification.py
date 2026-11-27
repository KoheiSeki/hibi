from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, get_args

CAPTURE_QUESTION_VERSION = "capture-classify-v1"

# 分類器が返してよい category。分類器の出力の約束なので、ai と modules の両方から使えるよう、
# ここに置く。値を足すときは、個別の定数と CaptureCategory を一緒に変える
CAPTURE_CATEGORY_SHOPPING = "shopping"
CAPTURE_CATEGORY_REMINDER = "reminder"
CAPTURE_CATEGORY_EXPENSE = "expense"
CAPTURE_CATEGORY_NOTE = "note"
CAPTURE_CATEGORY_CHAT = "chat"

CaptureCategory = Literal["shopping", "reminder", "expense", "note", "chat"]
CAPTURE_CATEGORIES: frozenset[str] = frozenset(get_args(CaptureCategory))

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
    async def classify_capture(self, text: str, *, question_version: str) -> Classification: ...


class ClarificationGenerator(Protocol):
    async def generate_clarification(self, text: str, *, category: str) -> str: ...


def normalize_clarification_text(text: str) -> str:
    if text.strip() == "" or len(text) > CLARIFICATION_TEXT_MAX_LENGTH:
        return CLARIFICATION_FALLBACK_TEXT
    return text
