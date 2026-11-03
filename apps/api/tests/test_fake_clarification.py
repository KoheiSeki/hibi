import pytest

from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.metrics import llm_call_count, reset_llm_call


@pytest.fixture(autouse=True)
def _reset_llm_calls() -> None:
    reset_llm_call()


@pytest.mark.asyncio
async def test_fake_clarification_counts_each_call() -> None:
    generator = FakeClarificationGenerator()

    await generator.generate_clarification("牛乳を買う", category="shopping")
    await generator.generate_clarification("牛乳を買う", category="shopping")

    assert llm_call_count() == 2


@pytest.mark.asyncio
async def test_llm_call_count_stays_zero_without_generation() -> None:
    assert llm_call_count() == 0


@pytest.mark.asyncio
async def test_fake_clarification_returns_category_question() -> None:
    question = await FakeClarificationGenerator().generate_clarification(
        "牛乳を買う",
        category="shopping",
    )

    assert question == "それはいつ買いますか？"  # noqa: RUF001
    assert llm_call_count() == 1


@pytest.mark.asyncio
async def test_fake_clarification_uses_template_for_unknown_category() -> None:
    question = await FakeClarificationGenerator().generate_clarification(
        "牛乳を買う",
        category="unknown",
    )

    assert question == "もう少し具体的に教えてください。"
