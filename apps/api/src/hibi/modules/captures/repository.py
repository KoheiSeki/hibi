from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.captures.models import CaptureModel
from hibi.modules.captures.types import Capture


class CaptureRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID, *, capture_id: UUID) -> Capture | None:
        stmt = select(CaptureModel).where(
            CaptureModel.id == capture_id, CaptureModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def get_by_idempotency_key(
        self, user_id: UUID, *, key: str
    ) -> Capture | None:
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
        stmt = stmt.order_by(
            CaptureModel.created_at.desc(), CaptureModel.id.desc()
        ).limit(limit)
        result = await self._session.execute(stmt)
        return [_to_capture(row) for row in result.scalars().all()]

    async def create_capture(
        self,
        user_id: UUID,
        *,
        capture_id: UUID,
        raw_text: str,
        idempotency_key: str,
        request_hash: str,
    ) -> Capture:
        db_obj = CaptureModel(
            id=capture_id,
            user_id=user_id,
            raw_text=raw_text,
            status="pending",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        self._session.add(db_obj)
        await self._session.flush()
        await self._session.refresh(db_obj)
        return _to_capture(db_obj)

    async def update_capture(
        self, user_id: UUID, *, capture_id: UUID, raw_text: str
    ) -> Capture | None:
        stmt = select(CaptureModel).where(
            CaptureModel.id == capture_id, CaptureModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        row.raw_text = raw_text
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_capture(row)

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


def _to_capture(row: CaptureModel) -> Capture:
    return Capture(
        id=row.id,
        user_id=row.user_id,
        raw_text=row.raw_text,
        status=row.status,
        idempotency_key=row.idempotency_key,
        request_hash=row.request_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
