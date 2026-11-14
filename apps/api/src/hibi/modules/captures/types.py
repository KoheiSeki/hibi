from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

CAPTURE_AGGREGATE_TYPE = "capture"
CAPTURE_PROCESSING_REQUESTED = "capture.processing_requested"

CAPTURE_STATUS_PENDING = "pending"
CAPTURE_STATUS_PROCESSING = "processing"
CAPTURE_STATUS_COMPLETED = "completed"
CAPTURE_STATUS_FAILED = "failed"

OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_PUBLISHED = "published"

CAPTURE_PROCESSING_MAX_ATTEMPTS = 3

CAPTURE_SEARCH_MODE_KEYWORD = "keyword"
CAPTURE_SEARCH_MODE_SEMANTIC = "semantic"
CAPTURE_SEARCH_LIMIT = 20

CaptureSearchMode = Literal["keyword", "semantic"]


@dataclass(frozen=True, slots=True)
class Capture:
    id: UUID
    user_id: UUID
    raw_text: str
    status: str
    idempotency_key: str
    request_hash: str
    processing_generation: int
    category: str | None
    route: str | None
    urgency: str | None
    confidence: Decimal | None
    policy_version: str | None
    question_version: str | None
    processed_at: datetime | None
    clarification_text: str | None
    created_at: datetime
    updated_at: datetime
    scenario: CaptureScenario | None = None


@dataclass(frozen=True, slots=True)
class CreateCaptureCommand:
    user_id: UUID
    raw_text: str  # 未 trim。呼び出し側の原文
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class CreateCaptureResult:
    capture: Capture
    created: bool  # True なら初回。Router が 201 / 200 に分ける


@dataclass(frozen=True, slots=True)
class UpdateCaptureCommand:
    user_id: UUID
    capture_id: UUID
    raw_text: str  # 未 trim


@dataclass(frozen=True, slots=True)
class ListCapturesQuery:
    user_id: UUID
    limit: int | None  # None なら 20
    cursor: str | None  # 不透明。無ければ先頭ページ


@dataclass(frozen=True, slots=True)
class SearchCapturesQuery:
    """Capture検索の入力。

    Attributes:
        user_id: 検証済みの所有者。検索はこのユーザーの行だけを対象にする。
        q: 検索語。router が1〜200文字で検証済み。
        mode: CAPTURE_SEARCH_MODE_KEYWORD か CAPTURE_SEARCH_MODE_SEMANTIC。
    """

    user_id: UUID
    q: str
    mode: str


@dataclass(frozen=True, slots=True)
class CapturePage:
    items: list[Capture]
    next_cursor: str | None
    has_next_page: bool


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    aggregate_id: UUID
    processing_generation: int


@dataclass(frozen=True, slots=True)
class CaptureScenario:
    route: str
    status: str
    title: str
    amount: int | None
    remind_text: str | None
    policy_version: str
    due_at: datetime | None = None
    done_at: datetime | None = None
