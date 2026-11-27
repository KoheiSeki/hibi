import re

_TOKEN_PATTERN = re.compile(r"[ぁ-ん]+|[ァ-ヶー]+|[一-龯]+|\d+")


def tokenize_text(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text)
