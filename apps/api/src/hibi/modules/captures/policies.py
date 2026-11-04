import re
from dataclasses import dataclass, replace
from decimal import Decimal

from hibi.ai.classification import CAPTURE_QUESTION_VERSION, Classification

CAPTURE_ROUTE_CONFIDENCE_THRESHOLD = Decimal("0.70")
CAPTURE_ROUTE_CLARIFY = "clarify"
CAPTURE_ROUTE_POLICY_VERSION = "capture-route-v1"

CAPTURE_CATEGORIES = frozenset({"shopping", "reminder", "expense", "note", "chat"})

CAPTURE_SCENARIO_POLICY_VERSION = "capture-scenario-v1"
CAPTURE_SCENARIO_STATUS_PROPOSED = "proposed"
CAPTURE_SCENARIO_ROUTES = frozenset({"shopping", "reminder", "expense"})

_EXACT_SCENARIOS: dict[tuple[str, str], tuple[str, int | None, str | None]] = {
    ("shopping", "牛乳を買う"): ("牛乳", None, None),
    ("shopping", "境界の牛乳"): ("牛乳", None, None),
    ("reminder", "明日の 9 時に起こして"): ("起こして", None, "明日の 9 時"),
    ("expense", "ランチ 1200 円"): ("ランチ", 1200, None),
}


@dataclass(frozen=True, slots=True)
class ScenarioProposal:
    route: str
    status: str
    title: str
    amount: int | None
    remind_text: str | None
    policy_version: str


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


def propose_capture_scenario(*, route: str, raw_text: str) -> ScenarioProposal | None:
    if route not in CAPTURE_SCENARIO_ROUTES:
        return None

    title, amount, remind_text = _EXACT_SCENARIOS.get(
        (route, raw_text),
        (raw_text.strip(), _expense_amount(route, raw_text), None),
    )
    return ScenarioProposal(
        route=route,
        status=CAPTURE_SCENARIO_STATUS_PROPOSED,
        title=title,
        amount=amount,
        remind_text=remind_text,
        policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
    )


def _expense_amount(route: str, raw_text: str) -> int | None:
    if route != "expense":
        return None
    matched = re.search(r"(\d+)\s*円", raw_text)
    if matched is None:
        return None
    return int(matched.group(1))
