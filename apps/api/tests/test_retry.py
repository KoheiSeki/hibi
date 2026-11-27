import pytest

from hibi.jobs import retry as retry_module


def test_retry_delay_uses_exponential_backoff_and_jitter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retry_module.random, "uniform", lambda _start, _end: 0.5)

    assert retry_module.retry_delay(1) == 5.5
    assert retry_module.retry_delay(2) == 10.5
