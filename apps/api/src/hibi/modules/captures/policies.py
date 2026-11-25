import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from hibi.ai.classification import (
    CAPTURE_CATEGORIES,
    CAPTURE_CATEGORY_CHAT,
    CAPTURE_QUESTION_VERSION,
    Classification,
)
from hibi.modules.captures.constants import (
    CAPTURE_ROUTE_CLARIFY,
    CAPTURE_ROUTE_EXPENSE,
    CAPTURE_ROUTE_REMINDER,
    CAPTURE_ROUTE_SHOPPING,
    CAPTURE_SCENARIO_ROUTES,
    CAPTURE_SCENARIO_STATUS_PROPOSED,
)
from hibi.modules.captures.due import extract_remind_text, parse_due_at

# 閾値と版は、ルールを変えたら一緒に変える値なので、ルールの隣に置く
CAPTURE_ROUTE_CONFIDENCE_THRESHOLD = Decimal("0.70")
CAPTURE_ROUTE_POLICY_VERSION = "capture-route-v1"
CAPTURE_SCENARIO_POLICY_VERSION = "capture-scenario-v1"

_EXACT_SCENARIOS: dict[tuple[str, str], tuple[str, int | None, str | None]] = {
    (CAPTURE_ROUTE_SHOPPING, "牛乳を買う"): ("牛乳", None, None),
    (CAPTURE_ROUTE_SHOPPING, "境界の牛乳"): ("牛乳", None, None),
    (CAPTURE_ROUTE_REMINDER, "明日の 9 時に起こして"): ("起こして", None, "明日の 9 時"),
    (CAPTURE_ROUTE_EXPENSE, "ランチ 1200 円"): ("ランチ", 1200, None),
}


@dataclass(frozen=True, slots=True)
class ScenarioProposal:
    """Worker が保存する、シナリオの提案 1 件。

    Attributes:
        route: shopping、reminder、expense のいずれか。
        status: 保存時は常に proposed。accepted にできるのは確認 API だけ。
        title: 画面に出すシナリオの題。
        amount: 円の整数。支出で金額が取れたときだけ。
        remind_text: 予定の時刻表現。reminder で取り出せたときだけ。
        policy_version: シナリオを作った policy の版。
        due_at: 期限。UTC の aware な datetime。reminder で解釈できたときだけ。
    """

    route: str
    status: str
    title: str
    amount: int | None
    remind_text: str | None
    policy_version: str
    due_at: datetime | None = None


def decide_capture_route(*, category: str, confidence: Decimal) -> str:
    """category と confidence から、処理の route を決める。

    confidence が閾値(0.70)以上なら category をそのまま route にする。
    未満なら clarify にして、聞き返しに回す。

    Args:
        category: 正規化済みの category。
        confidence: 分類の確信度。0 以上 1 以下。

    Returns:
        確定した category、または clarify。
    """

    if confidence >= CAPTURE_ROUTE_CONFIDENCE_THRESHOLD:
        return category
    return CAPTURE_ROUTE_CLARIFY


def normalize_classification(classification: Classification) -> Classification:
    """分類の結果が許可された形か確かめ、不正なら chat の確信度 0 に置き換える。

    category が未知、confidence が範囲外、question_version が現行と違うときは、
    例外にせず chat、確信度 0 にする。route は clarify になり、聞き返しで完了する。

    Args:
        classification: 分類器が返した結果。

    Returns:
        正しければ引数のまま。不正なら置き換えた結果。
    """

    if (
        classification.category not in CAPTURE_CATEGORIES
        or not Decimal("0") <= classification.confidence <= Decimal("1")
        or classification.question_version != CAPTURE_QUESTION_VERSION
    ):
        return replace(
            classification,
            category=CAPTURE_CATEGORY_CHAT,
            confidence=Decimal("0"),
            question_version=CAPTURE_QUESTION_VERSION,
        )

    return classification


def propose_capture_scenario(
    *, route: str, raw_text: str, now: datetime, timezone: str
) -> ScenarioProposal | None:
    """route が実行できるものなら、シナリオの提案を作る。

    shopping、reminder、expense だけが対象で、LLM は使わない。dataset にある本文は
    決まった値を優先し、それ以外は本文を trim した値を題にする。金額は expense、
    時刻の表現と期限は reminder のときだけ求める。

    Args:
        route: 確定した route。
        raw_text: Capture の本文。
        now: 現在時刻。aware な datetime。期限の計算にだけ使う。
        timezone: ユーザーの IANA 名。期限の計算にだけ使う。

    Returns:
        シナリオの提案。route が shopping、reminder、expense 以外なら None。
    """

    if route not in CAPTURE_SCENARIO_ROUTES:
        return None

    title, amount, remind_text = _EXACT_SCENARIOS.get(
        (route, raw_text),
        (raw_text.strip(), _expense_amount(route, raw_text), _remind_text(route, raw_text)),
    )
    due_at = parse_due_at(remind_text, now=now, timezone=timezone) if remind_text else None
    return ScenarioProposal(
        route=route,
        status=CAPTURE_SCENARIO_STATUS_PROPOSED,
        title=title,
        amount=amount,
        remind_text=remind_text,
        policy_version=CAPTURE_SCENARIO_POLICY_VERSION,
        due_at=due_at,
    )


def normalize_urgency_score(score: float) -> Decimal | None:
    """Jev の緊急度を、DB に保存できる小数 2 桁の Decimal に直す。

    保存先の `captures.urgency_score` は `numeric(3,2)` で、0 以上 1 以下の
    check がある。範囲外の値は保存せず None を返すので、呼び出し側は
    分類の完了を止めずに、緊急度だけを null で保存できる。float の誤差を
    避けるため、文字列を経由して Decimal にしてから、小数 2 桁に丸める。

    Args:
        score: Jev が返した緊急度。

    Returns:
        0 以上 1 以下なら、小数 2 桁の Decimal。範囲外、または NaN なら None。
    """

    if not 0 <= score <= 1:
        return None
    return Decimal(str(score)).quantize(Decimal("0.01"))


def _expense_amount(route: str, raw_text: str) -> int | None:
    """expense の本文から、円の直前にある整数を金額として取り出す。

    Args:
        route: 確定した route。expense 以外は金額を取らない。
        raw_text: Capture の本文。

    Returns:
        金額。expense でない、または `N円` の形が無ければ None。
    """

    if route != CAPTURE_ROUTE_EXPENSE:
        return None
    matched = re.search(r"(\d+)\s*円", raw_text)
    if matched is None:
        return None
    return int(matched.group(1))


def _remind_text(route: str, raw_text: str) -> str | None:
    """reminder の本文から、時刻の表現を取り出す。

    Args:
        route: 確定した route。reminder 以外は期限を持たない。
        raw_text: Capture の本文。

    Returns:
        時刻の表現。reminder でない、または表現が無ければ None。
    """

    if route != CAPTURE_ROUTE_REMINDER:
        return None
    return extract_remind_text(raw_text)
