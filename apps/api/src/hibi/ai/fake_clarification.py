from hibi.ai.classification import (
    CAPTURE_CATEGORY_EXPENSE,
    CAPTURE_CATEGORY_NOTE,
    CAPTURE_CATEGORY_REMINDER,
    CAPTURE_CATEGORY_SHOPPING,
    CLARIFICATION_FALLBACK_TEXT,
)
from hibi.ai.metrics import record_llm_call

# chat と未知の category は、ここに無いので CLARIFICATION_FALLBACK_TEXT になる
_QUESTIONS: dict[str, str] = {
    CAPTURE_CATEGORY_SHOPPING: "それはいつ買いますか？",  # noqa: RUF001
    CAPTURE_CATEGORY_REMINDER: "いつの予定ですか？",  # noqa: RUF001
    CAPTURE_CATEGORY_EXPENSE: "金額はいくらですか？",  # noqa: RUF001
    CAPTURE_CATEGORY_NOTE: "何を残しますか？",  # noqa: RUF001
}


class FakeClarificationGenerator:
    async def generate_clarification(self, text: str, *, category: str) -> str:
        record_llm_call()
        return _QUESTIONS.get(category, CLARIFICATION_FALLBACK_TEXT)
