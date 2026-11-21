from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.outbox.models import OutboxModel
from hibi.modules.outbox.types import OUTBOX_STATUS_PENDING, OUTBOX_STATUS_PUBLISHED, OutboxEvent


class OutboxRepository:
    """relay が使う、outbox の読み出しと配送済みの記録。

    対象の種類(Capture、ダイジェスト)を問わず、すべての outbox を扱う。行を足すのは、
    対象の行と同じ transaction で書く必要があるので、依頼する側の repository が行う。
    トランザクションは持たない。commit は呼び出し側が行う。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_pending_outbox_events(self, *, limit: int) -> list[OutboxEvent]:
        """配送待ちの outbox を、古い順に読む。

        `status` が pending で、`available_at` を過ぎた行が対象。`FOR UPDATE SKIP LOCKED`
        で読むので、relay が同時に動いても、同じ行を重複して取らない。行のロックは
        呼び出し側の transaction が終わるまで続く。

        Args:
            limit: 読む最大件数。

        Returns:
            `available_at`、`id` の昇順の OutboxEvent。
        """

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

    async def update_outbox_published(self, *, outbox_id: UUID) -> bool:
        """pending の outbox を、配送済みにする。

        Args:
            outbox_id: outbox の id。

        Returns:
            更新したら True。既に配送済み、または存在しなければ False。
        """

        stmt = (
            update(OutboxModel)
            .where(OutboxModel.id == outbox_id, OutboxModel.status == OUTBOX_STATUS_PENDING)
            .values(status=OUTBOX_STATUS_PUBLISHED, published_at=func.now())
            .returning(OutboxModel.id)
        )
        return await self._session.scalar(stmt) is not None


def _to_outbox_event(row: OutboxModel) -> OutboxEvent:
    """ORM の outbox の行を、ドメインの OutboxEvent に直す。

    Args:
        row: outbox の行。

    Returns:
        配送に必要な項目だけを持つ OutboxEvent。
    """

    return OutboxEvent(
        id=row.id,
        aggregate_id=row.aggregate_id,
        aggregate_type=row.aggregate_type,
        processing_generation=row.processing_generation,
    )
