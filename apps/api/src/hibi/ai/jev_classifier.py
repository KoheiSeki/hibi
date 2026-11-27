from decimal import Decimal

from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy, Score
from typesafe_sdk._core.errors import (
    TypeSafeAPIConnectionError,
    TypeSafeAPITimeoutError,
    TypeSafeInternalServerError,
)
from typesafe_sdk._core.response_types import ChoiceAnswer, ScoreAnswer

from hibi.ai.classification import (
    CAPTURE_CATEGORY_CHAT,
    CAPTURE_CATEGORY_EXPENSE,
    CAPTURE_CATEGORY_NOTE,
    CAPTURE_CATEGORY_REMINDER,
    CAPTURE_CATEGORY_SHOPPING,
    Classification,
    ClassificationTimeoutError,
)
from hibi.core.config import get_settings

# Jev に渡す、category ごとの判断基準。キーが Jev の返す category になる
_CATEGORY_CRITERIA: dict[str, str] = {
    CAPTURE_CATEGORY_SHOPPING: "買う、注文する、在庫を補う",
    CAPTURE_CATEGORY_REMINDER: "時刻や日付を伴う予定、想起",
    CAPTURE_CATEGORY_EXPENSE: "金額を伴う支出の記録",
    CAPTURE_CATEGORY_NOTE: "後で読む、保管する情報",
    CAPTURE_CATEGORY_CHAT: "会話、感想、上のどれにも決まらない雑談",
}


class JevCaptureClassifier:
    async def classify_capture(self, text: str, *, question_version: str) -> Classification:
        async with AsyncTypeSafeClient(
            api_key=get_settings().jev_api_key.get_secret_value(),
            model="jev-1.13.0",
            retry=RetryPolicy(max_retries=0),
        ) as client:
            try:
                result = await client.system_one(
                    state=text,
                    questions={
                        "category": Choice(
                            instructions="次の一文を、許可された category のどれか1つに分類する。",
                            criteria=_CATEGORY_CRITERIA,
                        ),
                        "urgency": Score(
                            instructions="この一文の緊急度を0から1で採点する。",
                            criteria=["急がない", "通常", "急ぐ"],
                        ),
                    },
                )
                category_answer: ChoiceAnswer | None = result.choices.get("category")
                urgency_answer: ScoreAnswer | None = result.scores.get("urgency")

                has_category: bool = (
                    category_answer is not None and category_answer.choice is not None
                )
                has_urgency: bool = urgency_answer is not None and urgency_answer.score is not None

                return Classification(
                    category=(result.choices["category"].choice if has_category else "unknown"),
                    confidence=(
                        Decimal(str(result.choices["category"].confidence))
                        if has_category
                        else Decimal("0")
                    ),
                    urgency_score=(result.scores["urgency"].score if has_urgency else 0.0),
                    question_version=question_version,
                )
            except (
                TypeSafeAPITimeoutError,
                TypeSafeAPIConnectionError,
                TypeSafeInternalServerError,
            ) as error:
                raise ClassificationTimeoutError() from error
