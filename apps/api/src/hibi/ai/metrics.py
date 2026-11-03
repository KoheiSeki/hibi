_llm_calls = 0


def record_llm_call() -> None:
    global _llm_calls
    _llm_calls += 1


def reset_llm_call() -> None:
    global _llm_calls
    _llm_calls = 0


def llm_call_count() -> int:
    return _llm_calls
