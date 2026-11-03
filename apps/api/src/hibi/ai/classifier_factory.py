from hibi.ai.classification import CaptureClassifier, ClarificationGenerator
from hibi.ai.fake_clarification import FakeClarificationGenerator
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.jev_classifier import JevCaptureClassifier
from hibi.ai.llm_clarification import LlmClarificationGenerator
from hibi.core.config import get_settings


def build_capture_classifier() -> CaptureClassifier:
    if get_settings().jev_api_key.get_secret_value().strip():
        return JevCaptureClassifier()
    return FakeCaptureClassifier()


def build_clarification_generator() -> ClarificationGenerator:
    if get_settings().open_ai_api_key.get_secret_value().strip():
        return LlmClarificationGenerator()
    return FakeClarificationGenerator()
