from hibi.ai.metrics import record_llm_call


class FakeClarificationGenerator:
    async def generate_clarification(self, text: str, *, category: str) -> str:
        record_llm_call()

        match category:
            case "shopping":
                return "それはいつ買いますか？"  # noqa: RUF001
            case "reminder":
                return "いつの予定ですか？"  # noqa: RUF001
            case "expense":
                return "金額はいくらですか？"  # noqa: RUF001
            case "note":
                return "何を残しますか？"  # noqa: RUF001
            case "chat":
                return "もう少し具体的に教えてください。"
            case _:
                return "もう少し具体的に教えてください。"
