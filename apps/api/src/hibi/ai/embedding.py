from dataclasses import dataclass
from typing import Protocol

CAPTURE_EMBED_DIMENSIONS = 8
CAPTURE_EMBED_VERSION = "capture-embed-v1"


@dataclass(frozen=True, slots=True)
class Embedding:
    vector: tuple[float, ...]
    model: str
    dimensions: int
    version: str


class TextEmbedder(Protocol):
    async def embed_text(self, text: str) -> Embedding: ...
