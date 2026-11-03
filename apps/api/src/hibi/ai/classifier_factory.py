from hibi.ai.classification import CaptureClassifier
from hibi.ai.fake_classifier import FakeCaptureClassifier
from hibi.ai.jev_classifier import JevCaptureClassifier
from hibi.core.config import get_settings


def build_capture_classifier() -> CaptureClassifier:
    if get_settings().jev_api_key.strip():
        return JevCaptureClassifier()
    return FakeCaptureClassifier()
