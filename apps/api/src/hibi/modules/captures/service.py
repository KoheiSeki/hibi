import hashlib
import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.classification import (
    CAPTURE_QUESTION_VERSION,
    CaptureClassifier,
    ClarificationGenerator,
    normalize_clarification_text,
)
from hibi.ai.embedding import Embedding, TextEmbedder
from hibi.modules.captures.errors import (
    CaptureNotEditableError,
    CaptureNotFoundError,
    CaptureNotRetryableError,
    CaptureTextInvalidError,
    IdempotencyKeyConflictError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    MalformedCursorError,
    ScenarioNotAcceptableError,
)
from hibi.modules.captures.policies import (
    CAPTURE_ROUTE_CLARIFY,
    CAPTURE_ROUTE_POLICY_VERSION,
    decide_capture_route,
    normalize_classification,
    propose_capture_scenario,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.search import rank_capture_by_keyword, rank_captures_by_semantic
from hibi.modules.captures.types import (
    CAPTURE_SEARCH_LIMIT,
    CAPTURE_SEARCH_MODE_SEMANTIC,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    Capture,
    CapturePage,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    UpdateCaptureCommand,
)

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x20-\x7E]{8,128}$")
_MAX_CAPTURE_LENGTH = 2_000


class CaptureService:
    def __init__(
        self,
        session: AsyncSession,
        repository: CaptureRepository,
        classifier: CaptureClassifier,
        generator: ClarificationGenerator,
        embedder: TextEmbedder,
    ) -> None:
        self._session = session
        self._repository = repository
        self._classifier = classifier
        self._generator = generator
        self._embedder = embedder

    async def create_capture(self, command: CreateCaptureCommand) -> CreateCaptureResult:
        idempotency_key = command.idempotency_key
        if idempotency_key is None or idempotency_key == "":
            raise IdempotencyKeyRequiredError()
        if _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            raise IdempotencyKeyInvalidError()

        stripped_raw_text = self._normalize_raw_text(command.raw_text)

        request_hash = hashlib.sha256(stripped_raw_text.encode("utf-8")).hexdigest()

        existing = await self._repository.get_by_idempotency_key(
            command.user_id, key=idempotency_key
        )
        result = self._replay_or_conflict(existing, request_hash)
        if result is not None:
            return result

        try:
            new = await self._repository.create_capture(
                command.user_id,
                capture_id=uuid7(),
                raw_text=stripped_raw_text,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                outbox_id=uuid7(),
            )
            return CreateCaptureResult(capture=new, created=True)
        except IntegrityError:
            await self._session.rollback()

            existing = await self._repository.get_by_idempotency_key(
                command.user_id, key=idempotency_key
            )
            result = self._replay_or_conflict(existing, request_hash)
            if result is not None:
                return result
            raise

    async def get_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        result = await self._repository.get_by_id(user_id, capture_id=capture_id)
        if result is None:
            raise CaptureNotFoundError(capture_id)
        return result

    async def list_captures(self, query: ListCapturesQuery) -> CapturePage:
        limit = 20 if query.limit is None else query.limit
        limit = min(max(limit, 1), 50)

        start_created_at = None
        start_capture_id = None
        if query.cursor is not None and query.cursor != "":
            start_created_at, start_capture_id = self._decode_cursor(query.cursor)

        rows = await self._repository.list_for_user(
            query.user_id,
            limit=limit + 1,
            start_created_at=start_created_at,
            start_capture_id=start_capture_id,
        )
        items = rows[:limit]
        has_next_page = len(rows) > limit
        next_cursor = None
        if has_next_page:
            last = items[-1]
            next_cursor = self._encode_cursor(last.created_at, last.id)

        return CapturePage(items=items, next_cursor=next_cursor, has_next_page=has_next_page)

    async def search_captures(self, query: SearchCapturesQuery) -> list[Capture]:
        """
        所有者の完了済みCaptureを、近い順に最大 CAPTURE_SEARCH_LIMIT 件返す。

        順位付けは search.py に任せる。mode が semantic ならクエリ文だけを
        embedder でベクトル化し、保存済みの embedding と比べる。本文の
        embedding は作り直さない。それ以外は TF-IDF のキーワード検索。
        0件なら空リストを返し、例外にはしない。

        Args:
            query: 所有者、検索語、検索方式。

        Returns:
            順位の高い順の Capture。scenario も含む。
        """

        documents = await self._repository.list_search_documents(query.user_id)

        if query.mode == CAPTURE_SEARCH_MODE_SEMANTIC:
            ranked = await rank_captures_by_semantic(
                documents, user_id=query.user_id, query=query.q, embedder=self._embedder
            )
        else:
            ranked = rank_capture_by_keyword(documents, user_id=query.user_id, query=query.q)
        capture_ids = ranked[:CAPTURE_SEARCH_LIMIT]
        if not capture_ids:
            return []

        captures = await self._repository.list_captures_by_ids(
            query.user_id, capture_ids=capture_ids
        )
        by_id = {capture.id: capture for capture in captures}
        return [by_id[capture_id] for capture_id in capture_ids if capture_id in by_id]

    async def update_capture(self, command: UpdateCaptureCommand) -> Capture:

        stripped_raw_text = self._normalize_raw_text(command.raw_text)

        updated = await self._repository.update_capture(
            command.user_id, capture_id=command.capture_id, raw_text=stripped_raw_text
        )

        if updated is not None:
            return updated

        current = await self._repository.get_by_id(command.user_id, capture_id=command.capture_id)
        if current is None:
            raise CaptureNotFoundError(capture_id=command.capture_id)

        raise CaptureNotEditableError()

    async def delete_capture(self, user_id: UUID, capture_id: UUID) -> None:
        is_deleted = await self._repository.delete_capture(user_id, capture_id=capture_id)
        if not is_deleted:
            raise CaptureNotFoundError(capture_id=capture_id)

    async def retry_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        retried = await self._repository.retry_failed_capture(
            user_id, capture_id=capture_id, outbox_id=uuid7()
        )
        if retried is not None:
            return retried

        current = await self._repository.get_by_id(user_id, capture_id=capture_id)
        if current is None:
            raise CaptureNotFoundError(capture_id)

        raise CaptureNotRetryableError()

    async def process_capture(self, capture_id: UUID, processing_generation: int) -> None:
        capture = await self._repository.get_by_capture_id(capture_id)
        if (
            capture is None
            or capture.processing_generation != processing_generation
            or capture.status in {CAPTURE_STATUS_COMPLETED, CAPTURE_STATUS_FAILED}
        ):
            return

        # statusをprocessingに更新
        is_started = await self._repository.update_processing_status(
            capture_id=capture_id,
            processing_generation=capture.processing_generation,
            expected_status=CAPTURE_STATUS_PENDING,
            status=CAPTURE_STATUS_PROCESSING,
        )
        if not is_started:
            return

        classification = await self._classifier.classify_capture(
            capture.raw_text,
            question_version=CAPTURE_QUESTION_VERSION,
        )
        normalized_classification = normalize_classification(classification)
        route = decide_capture_route(
            category=normalized_classification.category,
            confidence=normalized_classification.confidence,
        )
        clarification_text: str | None = None
        if route == CAPTURE_ROUTE_CLARIFY:
            generated = await self._generator.generate_clarification(
                capture.raw_text,
                category=normalized_classification.category,
            )
            clarification_text = normalize_clarification_text(generated)

        scenario = propose_capture_scenario(route=route, raw_text=capture.raw_text)

        embedding: Embedding | None = None
        if capture.raw_text.strip() != "":
            # hashの照合はcomplete_capture_classificationと同じraw_textで行う
            has_embedding = await self._repository.has_same_content_embedding(
                capture.user_id, capture_id=capture_id, text=capture.raw_text
            )
            if not has_embedding:
                embedding = await self._embedder.embed_text(capture.raw_text)

        await self._repository.complete_capture_classification(
            capture_id=capture_id,
            processing_generation=capture.processing_generation,
            category=normalized_classification.category,
            route=route,
            urgency="normal",
            confidence=normalized_classification.confidence,
            policy_version=CAPTURE_ROUTE_POLICY_VERSION,
            question_version=normalized_classification.question_version,
            clarification_text=clarification_text,
            scenario=scenario,
            embedding=embedding,
        )

    async def mark_processing_failed(self, capture_id: UUID, processing_generation: int) -> None:
        await self._repository.update_processing_status(
            capture_id=capture_id,
            processing_generation=processing_generation,
            expected_status=CAPTURE_STATUS_PENDING,
            status=CAPTURE_STATUS_FAILED,
        )

    async def accept_capture_scenario(self, user_id: UUID, capture_id: UUID) -> Capture:
        is_accepted = await self._repository.accept_capture_scenario(user_id, capture_id=capture_id)
        if is_accepted:
            capture = await self._repository.get_by_id(user_id, capture_id=capture_id)
            if capture is None:
                raise CaptureNotFoundError(capture_id)
            return capture

        current = await self._repository.get_by_id(user_id, capture_id=capture_id)
        scenario = None
        if current is not None:
            scenario = await self._repository.get_capture_scenario(user_id, capture_id=capture_id)
        if current is None or scenario is None:
            raise CaptureNotFoundError(capture_id)

        raise ScenarioNotAcceptableError()

    def _replay_or_conflict(
        self, existing: Capture | None, request_hash: str
    ) -> CreateCaptureResult | None:
        if existing is None:
            return None
        if existing.request_hash == request_hash:
            return CreateCaptureResult(capture=existing, created=False)
        raise IdempotencyKeyConflictError()

    def _normalize_raw_text(self, raw_text: str) -> str:
        stripped_raw_text = raw_text.strip()
        if len(stripped_raw_text) == 0 or len(stripped_raw_text) > _MAX_CAPTURE_LENGTH:
            raise CaptureTextInvalidError()
        return stripped_raw_text

    def _decode_cursor(self, cursor: str) -> tuple[datetime, UUID]:
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = urlsafe_b64decode(padded)
            payload = json.loads(raw)
            created_at = datetime.fromisoformat(str(payload["c"]).replace("Z", "+00:00"))
            capture_id = UUID(str(payload["i"]))
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            raise MalformedCursorError() from None

        if created_at.tzinfo is None:
            raise MalformedCursorError() from None
        return created_at, capture_id

    def _encode_cursor(self, created_at: datetime, capture_id: UUID) -> str:
        payload = {
            "c": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "i": str(capture_id),
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
