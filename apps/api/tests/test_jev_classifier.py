from decimal import Decimal
from types import SimpleNamespace

import pytest
from typesafe_sdk import TypeSafeAPITimeoutError

from hibi.ai import jev_classifier
from hibi.ai.classification import ClassificationTimeoutError
from hibi.ai.jev_classifier import JevCaptureClassifier


class _FakeClient:
    def __init__(self, *, result: object | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error
        self.state: str | None = None

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def system_one(self, *, state: str, questions: object) -> object:
        del questions
        self.state = state
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(jev_classifier, "AsyncTypeSafeClient", lambda **_kwargs: client)


@pytest.mark.asyncio
async def test_jev_classifier_maps_system_one_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient(
        result=SimpleNamespace(
            choices={
                "category": SimpleNamespace(choice="shopping", confidence=0.91),
            },
            scores={"urgency": SimpleNamespace(score=0.2)},
        )
    )
    _patch_client(monkeypatch, client)

    result = await JevCaptureClassifier().classify_capture(
        "牛乳を買う",
        question_version="capture-classify-v1",
    )

    assert client.state == "牛乳を買う"
    assert result.category == "shopping"
    assert result.confidence == Decimal("0.91")
    assert result.urgency_score == 0.2
    assert result.question_version == "capture-classify-v1"


@pytest.mark.asyncio
async def test_jev_classifier_raises_timeout_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(
        monkeypatch,
        _FakeClient(error=TypeSafeAPITimeoutError(1.0)),
    )

    with pytest.raises(ClassificationTimeoutError):
        await JevCaptureClassifier().classify_capture(
            "牛乳を買う",
            question_version="capture-classify-v1",
        )


@pytest.mark.asyncio
async def test_jev_classifier_returns_unknown_when_category_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        _FakeClient(result=SimpleNamespace(choices={}, scores={})),
    )

    result = await JevCaptureClassifier().classify_capture(
        "牛乳を買う",
        question_version="capture-classify-v1",
    )

    assert result.category == "unknown"
    assert result.confidence == Decimal("0")
    assert result.urgency_score == 0.0
