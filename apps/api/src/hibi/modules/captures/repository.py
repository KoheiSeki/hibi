from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.captures.models import CaptureModel, OutboxModel
from hibi.modules.captures.types import (
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    Capture,
    OutboxEvent,
)


class CaptureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_capture_id(self, capture_id: UUID) -> Capture | None:
        stmt = select(CaptureModel).where(CaptureModel.id == capture_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def get_by_id(self, user_id: UUID, *, capture_id: UUID) -> Capture | None:
        stmt = select(CaptureModel).where(
            CaptureModel.id == capture_id, CaptureModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def get_by_idempotency_key(self, user_id: UUID, *, key: str) -> Capture | None:
        stmt = select(CaptureModel).where(
            CaptureModel.user_id == user_id, CaptureModel.idempotency_key == key
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        start_created_at: datetime | None = None,
        start_capture_id: UUID | None = None,
    ) -> list[Capture]:
        stmt = select(CaptureModel).where(CaptureModel.user_id == user_id)
        if start_created_at is not None and start_capture_id is not None:
            stmt = stmt.where(
                tuple_(CaptureModel.created_at, CaptureModel.id)
                < (start_created_at, start_capture_id)
            )
        stmt = stmt.order_by(CaptureModel.created_at.desc(), CaptureModel.id.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_capture(row) for row in result.scalars().all()]

    async def list_pending_outbox_events(self, *, limit: int) -> list[OutboxEvent]:
        stmt = (
            select(OutboxModel)
            .where(
                OutboxModel.status == OUTBOX_STATUS_PENDING,
                OutboxModel.available_at <= func.now(),
            )
            .order_by(OutboxModel.available_at, OutboxModel.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self._session.execute(stmt)
        return [_to_outbox_event(row) for row in result.scalars()]

    async def create_capture(
        self,
        user_id: UUID,
        *,
        capture_id: UUID,
        raw_text: str,
        idempotency_key: str,
        request_hash: str,
        outbox_id: UUID,
    ) -> Capture:
        capture = CaptureModel(
            id=capture_id,
            user_id=user_id,
            raw_text=raw_text,
            status=CAPTURE_STATUS_PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        outbox = OutboxModel(id=outbox_id, user_id=user_id, aggregate_id=capture_id)
        self._session.add(capture)
        self._session.add(outbox)
        await self._session.flush()
        await self._session.refresh(capture)
        return _to_capture(capture)

    async def update_capture(
        self, user_id: UUID, *, capture_id: UUID, raw_text: str
    ) -> Capture | None:
        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.user_id == user_id,
                CaptureModel.status.in_([CAPTURE_STATUS_PENDING, CAPTURE_STATUS_FAILED]),
            )
            .values(raw_text=raw_text, updated_at=func.now())
            .returning(CaptureModel)
        )
        row = await self._session.scalar(stmt)
        if row is None:
            return None

        return _to_capture(row)

    async def update_processing_status(
        self,
        *,
        capture_id: UUID,
        processing_generation: int,
        expected_status: str,
        status: str,
    ) -> bool:
        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.status == expected_status,
                CaptureModel.processing_generation == processing_generation,
            )
            .values(status=status)
            .returning(CaptureModel.id)
        )
        return await self._session.scalar(stmt) is not None

    async def update_outbox_published(self, *, outbox_id: UUID) -> bool:
        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id == outbox_id, OutboxModel.status == OUTBOX_STATUS_PENDING)
            .values(status=OUTBOX_STATUS_PUBLISHED, published_at=func.now())
            .returning(OutboxModel.id)
        )
        return await self._session.scalar(stmt) is not None

    async def delete_capture(self, user_id: UUID, *, capture_id: UUID) -> bool:
        stmt = select(CaptureModel).where(
            CaptureModel.id == capture_id, CaptureModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False

        await self._session.delete(row)
        await self._session.flush()
        return True

    async def retry_failed_capture(
        self, user_id: UUID, *, capture_id: UUID, outbox_id: UUID
    ) -> Capture | None:
        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.user_id == user_id,
                CaptureModel.status == CAPTURE_STATUS_FAILED,
            )
            .values(
                status=CAPTURE_STATUS_PENDING,
                processing_generation=CaptureModel.processing_generation + 1,
                updated_at=func.now(),
            )
            .returning(CaptureModel)
        )

        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        self._session.add(
            OutboxModel(
                id=outbox_id,
                user_id=user_id,
                aggregate_id=capture_id,
                processing_generation=row.processing_generation,
            )
        )
        await self._session.flush()

        return _to_capture(row)

    async def complete_capture_classification(
        self,
        *,
        capture_id: UUID,
        processing_generation: int,
        category: str,
        route: str,
        urgency: str,
        confidence: Decimal,
        policy_version: str,
        question_version: str,
    ) -> Capture | None:
        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.status == CAPTURE_STATUS_PROCESSING,
                CaptureModel.processing_generation == processing_generation,
            )
            .values(
                status=CAPTURE_STATUS_COMPLETED,
                category=category,
                route=route,
                urgency=urgency,
                confidence=confidence,
                policy_version=policy_version,
                question_version=question_version,
                processed_at=func.now(),
                updated_at=func.now(),
            )
            .returning(CaptureModel)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        return _to_capture(row)


def _to_capture(row: CaptureModel) -> Capture:
    return Capture(
        id=row.id,
        user_id=row.user_id,
        raw_text=row.raw_text,
        status=row.status,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        processing_generation=row.processing_generation,
        category=row.category,
        route=row.route,
        urgency=row.urgency,
        confidence=row.confidence,
        policy_version=row.policy_version,
        question_version=row.question_version,
        processed_at=row.processed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_outbox_event(row: OutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=row.id,
        aggregate_id=row.aggregate_id,
        processing_generation=row.processing_generation,
    )
