from dataclasses import dataclass
from datetime import datetime
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


@dataclass(frozen=True, slots=True)
class Capture:
    id: UUID
    user_id: UUID
    raw_text: str
    status: str
    idempotency_key: str
    request_hash: str
    processing_generation: int
    created_at: datetime
    updated_at: datetime


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
class CapturePage:
    items: list[Capture]
    next_cursor: str | None
    has_next_page: bool


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    id: UUID
    aggregate_id: UUID
    processing_generation: int
