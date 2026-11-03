import pytest

from hibi.ai.classification import CLARIFICATION_TEXT_MAX_LENGTH
from hibi.ai.llm_clarification import LlmClarificationGenerator
from hibi.core.config import get_settings


@pytest.mark.integration
@pytest.mark.asyncio
async def test_llm_clarification_returns_a_question() -> None:
    if not get_settings().open_ai_api_key.get_secret_value().strip():
        pytest.skip("HIBI_OPEN_AI_API_KEY is not configured")

    question = await LlmClarificationGenerator().generate_clarification(
        "牛乳",
        category="shopping",
    )

    assert question.strip()
    assert len(question) <= CLARIFICATION_TEXT_MAX_LENGTH
