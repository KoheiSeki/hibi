from decimal import Decimal

CAPTURE_ROUTE_CONFIDENCE_THRESHOLD = Decimal("0.70")
CAPTURE_ROUTE_CLARIFY = "clarify"


def decide_capture_route(*, category: str, confidence: Decimal) -> str:
    if confidence >= CAPTURE_ROUTE_CONFIDENCE_THRESHOLD:
        return category
    return CAPTURE_ROUTE_CLARIFY
