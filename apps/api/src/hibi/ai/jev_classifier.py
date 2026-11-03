from decimal import Decimal
from typesafe_sdk._core.errors import (
    TypeSafeAPIConnectionError,
    TypeSafeAPITimeoutError,
    TypeSafeInternalServerError,
)
from typesafe_sdk._core.response_types import ChoiceAnswer, ScoreAnswer
from hibi.ai.classification import (
    Classification,
    ClassificationTimeoutError,
)
from typesafe_sdk import AsyncTypeSafeClient, Choice, RetryPolicy, Score


class JevCaptureClassifier:
    async def classify_capture(
        self, text: str, *, question_version: str
    ) -> Classification:
        async with AsyncTypeSafeClient(
            model="jev-1.13.0", retry=RetryPolicy(max_retries=0)
        ) as client:
            try:
                result = await client.system_one(
                    state=text,
                    questions={
                        "category": Choice(
                            instructions="次の一文を、許可された category のどれか1つに分類する。",
                            criteria={
                                "shopping": "買う、注文する、在庫を補う",
                                "reminder": "時刻や日付を伴う予定、想起",
                                "expense": "金額を伴う支出の記録",
                                "note": "後で読む、保管する情報",
                                "chat": "会話、感想、上のどれにも決まらない雑談",
                            },
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
                has_urgency: bool = (
                    urgency_answer is not None and urgency_answer.score is not None
                )

                return Classification(
                    category=(
                        result.choices["category"].choice if has_category else "unknown"
                    ),
                    confidence=(
                        Decimal(str(result.choices["category"].confidence))
                        if has_category
                        else Decimal("0")
                    ),
                    urgency_score=(
                        result.scores["urgency"].score if has_urgency else 0.0
                    ),
                    question_version=question_version,
                )
            except (
                TypeSafeAPITimeoutError,
                TypeSafeAPIConnectionError,
                TypeSafeInternalServerError,
            ):
                raise ClassificationTimeoutError()
