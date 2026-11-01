from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    confidence: Decimal
    urgency_score: float
    question_version: str
