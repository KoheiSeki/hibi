import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.embedding import Embedding
from hibi.modules.captures.models import (
    CaptureEmbeddingModel,
    CaptureModel,
    CaptureScenarioModel,
    OutboxModel,
)
from hibi.modules.captures.policies import (
    CAPTURE_SCENARIO_STATUS_ACCEPTED,
    CAPTURE_SCENARIO_STATUS_PROPOSED,
    ScenarioProposal,
)
from hibi.modules.captures.search import SearchDocument
from hibi.modules.captures.types import (
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    OUTBOX_STATUS_PENDING,
    OUTBOX_STATUS_PUBLISHED,
    Capture,
    CaptureScenario,
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
        scenario_row = await self.get_capture_scenario(user_id, capture_id=capture_id)
        return _to_capture(row, scenario_row)

    async def get_by_idempotency_key(self, user_id: UUID, *, key: str) -> Capture | None:
        stmt = select(CaptureModel).where(
            CaptureModel.user_id == user_id, CaptureModel.idempotency_key == key
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def get_capture_scenario(
        self, user_id: UUID, *, capture_id: UUID
    ) -> CaptureScenarioModel | None:
        stmt = select(CaptureScenarioModel).where(
            CaptureScenarioModel.capture_id == capture_id,
            CaptureScenarioModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

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
        rows = result.scalars().all()
        if not rows:
            return []

        scenario_result = await self._session.execute(
            select(CaptureScenarioModel).where(
                CaptureScenarioModel.user_id == user_id,
                CaptureScenarioModel.capture_id.in_([row.id for row in rows]),
            )
        )
        scenarios = {scenario.capture_id: scenario for scenario in scenario_result.scalars()}
        return [_to_capture(row, scenarios.get(row.id)) for row in rows]

    async def list_search_documents(self, user_id: UUID) -> list[SearchDocument]:
        """
        検索の候補を読み出す。所有者の completed 行だけを返す。

        embedding が無い行も候補に残す。outer join を使う。キーワード検索は
        embedding を使わないので、無い行も当たる必要がある。意味検索は
        search.py 側で embedding が無い行を除く。

        Args:
            user_id: 所有者。別ユーザーの行は読まない。

        Returns:
            新しい順の SearchDocument。
        """

        stmt = (
            select(CaptureModel, CaptureEmbeddingModel)
            .outerjoin(CaptureEmbeddingModel, CaptureEmbeddingModel.capture_id == CaptureModel.id)
            .where(CaptureModel.user_id == user_id, CaptureModel.status == CAPTURE_STATUS_COMPLETED)
            .order_by(CaptureModel.created_at.desc(), CaptureModel.id.desc())
        )
        result = await self._session.execute(stmt)
        return [
            SearchDocument(
                capture_id=row.id,
                user_id=row.user_id,
                status=row.status,
                text=row.raw_text,
                embedding=_to_embedding(embedding_row),
            )
            for row, embedding_row in result.all()
        ]

    async def list_captures_by_ids(
        self, user_id: UUID, *, capture_ids: Sequence[UUID]
    ) -> list[Capture]:
        """
        id の一覧から、所有者の Capture を scenario 付きで読む。

        返す順序は保証しない。SQL の IN は順序を持たない。呼び出し側が
        順位に合わせて並べ直す。所有者が違う id は黙って落とす。

        Args:
            user_id: 所有者。
            capture_ids: 読みたい Capture の id。空なら DB を叩かず空を返す。

        Returns:
            見つかった Capture。
        """

        if not capture_ids:
            return []

        stmt = (
            select(CaptureModel, CaptureScenarioModel)
            .outerjoin(CaptureScenarioModel, CaptureScenarioModel.capture_id == CaptureModel.id)
            .where(CaptureModel.user_id == user_id, CaptureModel.id.in_(capture_ids))
        )
        result = await self._session.execute(stmt)
        return [_to_capture(row, scenario_row) for row, scenario_row in result.all()]

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
        clarification_text: str | None,
        scenario: ScenarioProposal | None = None,
        embedding: Embedding | None = None,
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
                clarification_text=clarification_text,
                updated_at=func.now(),
            )
            .returning(CaptureModel)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None

        if scenario is not None:
            self._session.add(
                CaptureScenarioModel(
                    capture_id=row.id,
                    user_id=row.user_id,
                    route=scenario.route,
                    status=scenario.status,
                    title=scenario.title,
                    amount=scenario.amount,
                    remind_text=scenario.remind_text,
                    policy_version=scenario.policy_version,
                    created_at=func.now(),
                    updated_at=func.now(),
                )
            )

        if embedding is not None:
            content_hash = hashlib.sha256(row.raw_text.encode("utf-8")).hexdigest()
            existing = await self._session.get(CaptureEmbeddingModel, row.id)
            if existing is None:
                self._session.add(
                    CaptureEmbeddingModel(
                        capture_id=row.id,
                        user_id=row.user_id,
                        content_text=row.raw_text,
                        content_hash=content_hash,
                        embedding=list(embedding.vector),
                        embedding_model=embedding.model,
                        embedding_dimensions=embedding.dimensions,
                        embedding_version=embedding.version,
                        created_at=func.now(),
                        updated_at=func.now(),
                    )
                )
            elif existing.content_hash != content_hash:
                existing.content_text = row.raw_text
                existing.content_hash = content_hash
                existing.embedding = list(embedding.vector)
                existing.embedding_model = embedding.model
                existing.embedding_dimensions = embedding.dimensions
                existing.embedding_version = embedding.version
                existing.updated_at = func.now()

        if scenario is not None or embedding is not None:
            await self._session.flush()

        return _to_capture(row)

    async def accept_capture_scenario(self, user_id: UUID, *, capture_id: UUID) -> bool:
        stmt = (
            update(CaptureScenarioModel)
            .where(
                CaptureScenarioModel.user_id == user_id,
                CaptureScenarioModel.capture_id == capture_id,
                CaptureScenarioModel.status == CAPTURE_SCENARIO_STATUS_PROPOSED,
            )
            .values(status=CAPTURE_SCENARIO_STATUS_ACCEPTED, updated_at=func.now())
            .returning(CaptureScenarioModel)
        )
        return await self._session.scalar(stmt) is not None

    async def has_same_content_embedding(
        self, user_id: UUID, *, capture_id: UUID, text: str
    ) -> bool:
        stmt = select(CaptureEmbeddingModel).where(
            CaptureEmbeddingModel.capture_id == capture_id,
            CaptureEmbeddingModel.user_id == user_id,
            CaptureEmbeddingModel.content_hash == hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        return await self._session.scalar(stmt) is not None


def _to_capture(row: CaptureModel, scenario_row: CaptureScenarioModel | None = None) -> Capture:
    scenario = None
    if scenario_row is not None:
        scenario = CaptureScenario(
            route=scenario_row.route,
            status=scenario_row.status,
            title=scenario_row.title,
            amount=scenario_row.amount,
            remind_text=scenario_row.remind_text,
            policy_version=scenario_row.policy_version,
        )

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
        clarification_text=row.clarification_text,
        created_at=row.created_at,
        updated_at=row.updated_at,
        scenario=scenario,
    )


def _to_outbox_event(row: OutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=row.id,
        aggregate_id=row.aggregate_id,
        processing_generation=row.processing_generation,
    )


def _to_embedding(row: CaptureEmbeddingModel | None = None) -> Embedding | None:
    if row is None:
        return None
    return Embedding(
        vector=tuple(row.embedding),
        model=row.embedding_model,
        dimensions=row.embedding_dimensions,
        version=row.embedding_version,
    )
