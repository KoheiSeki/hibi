from dataclasses import replace
from decimal import Decimal

from hibi.ai.classification import CAPTURE_QUESTION_VERSION, Classification

CAPTURE_ROUTE_CONFIDENCE_THRESHOLD = Decimal("0.70")
CAPTURE_ROUTE_CLARIFY = "clarify"

CAPTURE_ROUTE_POLICY_VERSION = "capture-route-v1"

CAPTURE_CATEGORIES = frozenset({"shopping", "reminder", "expense", "note", "chat"})


def decide_capture_route(*, category: str, confidence: Decimal) -> str:
    if confidence >= CAPTURE_ROUTE_CONFIDENCE_THRESHOLD:
        return category
    return CAPTURE_ROUTE_CLARIFY


def normalize_classification(classification: Classification) -> Classification:
    if (
        classification.category not in CAPTURE_CATEGORIES
        or not Decimal("0") <= classification.confidence <= Decimal("1")
        or classification.question_version != CAPTURE_QUESTION_VERSION
    ):
        return replace(
            classification,
            category="chat",
            confidence=Decimal("0"),
            question_version=CAPTURE_QUESTION_VERSION,
        )

    return classification
