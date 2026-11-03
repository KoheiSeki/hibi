from collections.abc import Iterable
from typing import Protocol

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam
from pydantic import BaseModel, ConfigDict, ValidationError

from hibi.ai.classification import (
    CLARIFICATION_FALLBACK_TEXT,
    ClarificationProviderError,
    normalize_clarification_text,
)
from hibi.ai.metrics import record_llm_call
from hibi.core.config import get_settings


class ClarificationModelClient(Protocol):
    async def complete_json(self, *, text: str, category: str) -> str: ...


class SdkClarificationClient:
    async def complete_json(self, *, text: str, category: str) -> str:
        client = AsyncOpenAI(
            api_key=get_settings().open_ai_api_key.get_secret_value(),
            base_url=get_settings().open_ai_base_url or None,
            timeout=get_settings().open_ai_timeout_seconds,
            max_retries=0,
        )

        messages: Iterable[ChatCompletionMessageParam] = [
            {
                "role": "system",
                "content": (
                    "聞き返しを1つだけ作る。"
                    '返答は {"question":"..."} だけにする。'
                    "question は500文字以内にする。"
                ),
            },
            {
                "role": "user",
                "content": f"category: {category}\n本文: {text}",
            },
        ]
        try:
            completion = await client.chat.completions.create(
                model=get_settings().open_ai_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            return content if content is not None else ""
        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as error:
            raise ClarificationProviderError() from error


class ClarificationOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str


class LlmClarificationGenerator:
    def __init__(self, client: ClarificationModelClient | None = None) -> None:
        self._client = client or SdkClarificationClient()

    async def generate_clarification(self, text: str, *, category: str) -> str:
        record_llm_call()
        raw = await self._client.complete_json(text=text, category=category)
        return _clarification_text_from_output(raw)


def _clarification_text_from_output(raw: str) -> str:
    try:
        question = ClarificationOutput.model_validate_json(raw).question
    except ValidationError:
        return CLARIFICATION_FALLBACK_TEXT
    return normalize_clarification_text(question)
