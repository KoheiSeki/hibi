from types import SimpleNamespace

from pydantic import SecretStr

from hibi.ai import classifier_factory
from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
)
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.jev_classifier import JevCaptureClassifier
from hibi.ai.llm_clarification import LlmClarificationGenerator


def test_build_capture_classifier_uses_fake_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(jev_api_key=SecretStr("")),
    )

    assert isinstance(build_capture_classifier(), FakeCaptureClassifier)


def test_build_capture_classifier_uses_jev_when_api_key_is_set(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(jev_api_key=SecretStr("test-key")),
    )

    assert isinstance(build_capture_classifier(), JevCaptureClassifier)


def test_build_clarification_generator_uses_fake_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(open_ai_api_key=SecretStr("")),
    )

    assert isinstance(build_clarification_generator(), FakeClarificationGenerator)


def test_build_clarification_generator_uses_llm_when_api_key_is_set(monkeypatch) -> None:
    monkeypatch.setattr(
        classifier_factory,
        "get_settings",
        lambda: SimpleNamespace(open_ai_api_key=SecretStr("test-key")),
    )

    assert isinstance(build_clarification_generator(), LlmClarificationGenerator)
