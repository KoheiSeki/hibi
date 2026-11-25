import hashlib
from collections.abc import Callable, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.embedding import Embedding
from hibi.modules.captures.constants import (
    CAPTURE_AGGREGATE_TYPE,
    CAPTURE_PROCESSING_REQUESTED,
    CAPTURE_SCENARIO_STATUS_ACCEPTED,
    CAPTURE_SCENARIO_STATUS_PROPOSED,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
)
from hibi.modules.captures.models import (
    CaptureEmbeddingModel,
    CaptureModel,
    CaptureScenarioModel,
)
from hibi.modules.captures.policies import ScenarioProposal
from hibi.modules.captures.search import SearchDocument
from hibi.modules.captures.today import TodayCandidate
from hibi.modules.captures.types import (
    Capture,
    CaptureScenario,
)
from hibi.modules.outbox.models import OutboxModel


class CaptureRepository:
    """Capture と、それに付くシナリオ、embedding、outbox の永続化。

    API から呼ぶ読み書きは、すべて `user_id` を条件に含める。`user_id` を取らないのは、
    Worker が `capture_id` と処理世代で操作するメソッドと、outbox の操作だけ。
    更新は条件付き UPDATE で行い、対象でなければ None か False を返す。例外にはしない。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_capture_id(self, capture_id: UUID) -> Capture | None:
        """所有者を問わず、id で Capture を 1 件読む。

        Worker が job の引数の `capture_id` だけで読むために使う。API からは使わない。
        シナリオは付けない。

        Args:
            capture_id: Capture の id。

        Returns:
            見つかった Capture。無ければ None。
        """

        stmt = select(CaptureModel).where(CaptureModel.id == capture_id)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return _to_capture(row)

    async def get_by_id(self, user_id: UUID, *, capture_id: UUID) -> Capture | None:
        """所有者の Capture を、シナリオ付きで 1 件読む。

        Args:
            user_id: 所有者。別ユーザーの行は読まない。
            capture_id: Capture の id。

        Returns:
            見つかった Capture。無い、または別ユーザーの行なら None。
        """

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
        """冪等キーで、所有者の Capture を 1 件読む。

        作成 API が、同じキーの再送か、本文が違う衝突かを判定するために使う。
        シナリオは付けない。

        Args:
            user_id: 所有者。
            key: 作成時に受け取った冪等キー。

        Returns:
            見つかった Capture。無ければ None。
        """

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
        """所有者の Capture に付くシナリオの行を読む。

        他のメソッドと違い、ドメインの型ではなく ORM のモデルを返す。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。

        Returns:
            シナリオの行。無い、または別ユーザーの行なら None。
        """

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
        """所有者の Capture を、新しい順に読む。

        並びは `created_at` と `id` の降順で、続きは keyset で読む。次のページの
        開始位置は、前のページの最後の行の `created_at` と `id` で渡す。2 つが両方
        揃ったときだけ、その位置より古い行から読む。シナリオは、ページ全体を
        1 回の追加クエリでまとめて読む。

        Args:
            user_id: 所有者。
            limit: 読む最大件数。
            start_created_at: 開始位置の作成時刻。
            start_capture_id: 開始位置の id。

        Returns:
            新しい順の Capture。無ければ空のリスト。
        """

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
        """検索の候補を読み出す。所有者の completed 行だけを返す。

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
        """id の一覧から、所有者の Capture を scenario 付きで読む。

        Today、検索、日次ダイジェストが、順位付けで求めた id から、画面や内容に出す
        Capture を引くのに使う。

        返す順序は保証しない。SQL の IN は順序を持たない。呼び出し側が
        順位に合わせて並べ直す。所有者が違う id と、順位付けのあとに削除された id は、
        黙って落とすので、返る件数は `capture_ids` より少ないことがある。

        Args:
            user_id: 所有者。
            capture_ids: 読みたい Capture の id。空なら DB を叩かず空を返す。

        Returns:
            見つかった Capture。scenario が無い Capture は `scenario` が None。
            1 件も無ければ空のリスト。
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

    async def list_open_scenario_candidates(self, user_id: UUID) -> list[TodayCandidate]:
        """未完了のシナリオを、Today とダイジェストの候補として読む。

        completed の Capture で、シナリオが付き、`done_at` が null の行が対象。
        シナリオが proposed か accepted かは問わない。期限による絞り込みは SQL では
        行わない。今日の終わりの判定は夏時間を含むため、`rank_today` と `count_deadlines`
        の側で、ユーザーの timezone を使って行う。そのため、期限が明日以降の行や、
        期限が過ぎた行も返す。

        Today の一覧と、日次ダイジェストの `items`、期限の件数が、同じ候補を読む。
        読む条件を変えると、両方の結果が変わる。

        Args:
            user_id: 所有者。別ユーザーの行は読まない。

        Returns:
            優先度の計算と、期限の数え上げに必要な項目だけを持つ TodayCandidate。
            並びは保証しない。順位付けは `rank_today` が行う。対象が無ければ空のリスト。
        """

        stmt = (
            select(
                CaptureScenarioModel.capture_id,
                CaptureModel.urgency_score,
                CaptureScenarioModel.due_at,
                CaptureModel.created_at,
            )
            .join(CaptureModel, CaptureModel.id == CaptureScenarioModel.capture_id)
            .where(
                CaptureModel.user_id == user_id,
                CaptureModel.status == CAPTURE_STATUS_COMPLETED,
                CaptureScenarioModel.done_at.is_(None),
            )
        )
        result = await self._session.execute(stmt)
        return [
            TodayCandidate(
                capture_id=capture_id,
                urgency_score=urgency_score,
                due_at=due_at,
                created_at=created_at,
            )
            for capture_id, urgency_score, due_at, created_at in result.all()
        ]

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
        """Capture と outbox の行を、同じ transaction で作る。

        Capture は pending で作る。API の応答を待たせずに、Worker の処理を
        予約するため、2 行を一緒に flush する。同じ所有者と冪等キーの行が既にあれば、
        flush で IntegrityError になる。呼び出し側が、再送か衝突かを判定する。

        Args:
            user_id: 所有者。
            capture_id: 新しい Capture の id。
            raw_text: 検証済みの本文。
            idempotency_key: 冪等キー。
            request_hash: 本文から求めた hash。再送と衝突の判定に使う。
            outbox_id: 新しい outbox の id。

        Returns:
            作った Capture。
        """

        capture = CaptureModel(
            id=capture_id,
            user_id=user_id,
            raw_text=raw_text,
            status=CAPTURE_STATUS_PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        outbox = OutboxModel(
            id=outbox_id,
            user_id=user_id,
            aggregate_id=capture_id,
            aggregate_type=CAPTURE_AGGREGATE_TYPE,
            event_type=CAPTURE_PROCESSING_REQUESTED,
        )
        self._session.add(capture)
        self._session.add(outbox)
        await self._session.flush()
        await self._session.refresh(capture)
        return _to_capture(capture)

    async def update_capture(
        self, user_id: UUID, *, capture_id: UUID, raw_text: str
    ) -> Capture | None:
        """所有者の本文を更新する。pending と failed の行だけが対象。

        更新できる状態を、UPDATE の条件に含める。処理中や完了済みの行は更新しない。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。
            raw_text: 検証済みの新しい本文。

        Returns:
            更新後の Capture。対象でなければ None。存在しないのか、更新できない
            状態なのかは区別しないので、呼び出し側が `get_by_id` で判別する。
        """

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
        """処理状態を、期待する状態のときだけ別の状態へ進める。

        `status` と `processing_generation` が両方一致するときだけ更新する。古い世代の
        job や、別の job が先に進めた行は更新されない。

        Args:
            capture_id: Capture の id。
            processing_generation: job の引数の処理世代。
            expected_status: 更新前に期待する状態。
            status: 更新後の状態。

        Returns:
            更新したら True。条件に合う行が無ければ False。
        """

        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.status == expected_status,
                CaptureModel.processing_generation == processing_generation,
            )
            .values(status=status, updated_at=func.now())
            .returning(CaptureModel.id)
        )
        return await self._session.scalar(stmt) is not None

    async def delete_capture(self, user_id: UUID, *, capture_id: UUID) -> bool:
        """所有者の Capture を削除する。

        シナリオと embedding は外部キーの `on delete cascade` で消える。outbox は外部キーが
        無いので、同じ transaction で明示的に消す。Capture が消えなかったとき(無い、または
        別ユーザーの行)は、outbox にも触れない。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。

        Returns:
            削除したら True。無い、または別ユーザーの行なら False。
        """

        stmt = (
            delete(CaptureModel)
            .where(
                CaptureModel.id == capture_id,
                CaptureModel.user_id == user_id,
            )
            .returning(CaptureModel.id)
        )
        deleted_id = await self._session.scalar(stmt)
        if deleted_id is None:
            return False

        await self._session.execute(
            delete(OutboxModel).where(
                OutboxModel.aggregate_type == CAPTURE_AGGREGATE_TYPE,
                OutboxModel.aggregate_id == capture_id,
            )
        )
        return True

    async def retry_failed_capture(
        self, user_id: UUID, *, capture_id: UUID, outbox_id: UUID
    ) -> Capture | None:
        """failed の Capture を、次の世代の pending に戻して再処理を予約する。

        `processing_generation` を 1 増やし、その世代の outbox を同じ transaction で
        足す。古い世代の job は、世代が合わず、何も変えない。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。
            outbox_id: 新しい outbox の id。

        Returns:
            戻した Capture。failed でない、または所有者が違えば None。
        """

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
                aggregate_type=CAPTURE_AGGREGATE_TYPE,
                event_type=CAPTURE_PROCESSING_REQUESTED,
                processing_generation=row.processing_generation,
            )
        )
        await self._session.flush()

        return _to_capture(row)

    async def recover_stalled_captures(
        self, *, stalled_before: datetime, outbox_id_factory: Callable[[], UUID]
    ) -> int:
        """processing のまま止まった Capture を、次の世代の pending に戻して再処理を予約する。

        worker が job の途中で落ちると、行は processing のまま残り、誰も進めない。
        `updated_at` が `stalled_before` より前の processing の行を、止まったと見なす。
        `retry_failed_capture` と同じく、`processing_generation` を 1 増やし、その世代の
        outbox を同じ transaction で足す。利用者の操作ではなくシステムが戻すので、
        所有者では絞らず、全ユーザーの行を対象にする。

        世代を進めるのは、止まったと見なした job が、実は遅れて動いていた場合に備えるため。
        古い世代の job は、世代が合わず、行を何も変えない。`updated_at` も今にするので、
        戻した行が、次の回復の実行で、すぐにまた拾われることはない。

        戻すのは `UPDATE ... RETURNING` の 1 回で、条件に合う行だけが変わる。回復が
        同時に 2 つ走っても、同じ行を 2 回戻すことはなく、outbox も行ごとに 1 件になる。
        pending、completed、failed の行には触れない。

        Args:
            stalled_before: これより前に更新された processing の行を、止まったと見なす。
                呼び出し側が、今から `STALLED_AFTER` を引いて渡す。
            outbox_id_factory: 戻した行ごとに呼び、新しい outbox の id を発行する。
                戻した行が無ければ呼ばない。

        Returns:
            戻した行の数。止まった行が無ければ 0。
        """

        stmt = (
            update(CaptureModel)
            .where(
                CaptureModel.status == CAPTURE_STATUS_PROCESSING,
                CaptureModel.updated_at < stalled_before,
            )
            .values(
                status=CAPTURE_STATUS_PENDING,
                processing_generation=CaptureModel.processing_generation + 1,
                updated_at=func.now(),
            )
            .returning(CaptureModel)
        )
        rows = (await self._session.scalars(stmt)).all()
        for row in rows:
            self._session.add(
                OutboxModel(
                    id=outbox_id_factory(),
                    user_id=row.user_id,
                    aggregate_type=CAPTURE_AGGREGATE_TYPE,
                    aggregate_id=row.id,
                    event_type=CAPTURE_PROCESSING_REQUESTED,
                    processing_generation=row.processing_generation,
                )
            )
        await self._session.flush()
        return len(rows)

    async def complete_capture_classification(
        self,
        *,
        capture_id: UUID,
        processing_generation: int,
        category: str,
        route: str,
        urgency: str,
        urgency_score: Decimal | None,
        confidence: Decimal,
        policy_version: str,
        question_version: str,
        clarification_text: str | None,
        scenario: ScenarioProposal | None = None,
        embedding: Embedding | None = None,
    ) -> Capture | None:
        """処理中の Capture を、分類の結果と一緒に completed にする。

        `status` が processing で、`processing_generation` も一致するときだけ
        更新する。分類の列、緊急度、聞き返し文を同じ UPDATE で書き、続けて、
        シナリオと embedding を同じ transaction で書く。

        embedding は、行が無ければ作り、本文の hash が違えば置き換え、同じなら
        そのまま残す。

        Args:
            capture_id: Capture の id。
            processing_generation: job の引数の処理世代。
            category: 正規化済みの category。
            route: 確定した route。
            urgency: 緊急度の label。
            urgency_score: 保存する緊急度。範囲外なら None。
            confidence: 分類の確信度。
            policy_version: route の policy の版。
            question_version: 分類の質問の版。
            clarification_text: 聞き返し文。clarify でなければ None。
            scenario: 保存するシナリオの提案。無ければ None。
            embedding: 保存する embedding。作らなかったときは None。

        Returns:
            完了した Capture。シナリオは付かない。対象でなければ None。
        """

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
                urgency_score=urgency_score,
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
                    due_at=scenario.due_at,
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

    async def set_scenario_done(self, user_id: UUID, *, capture_id: UUID, done: bool) -> bool:
        """所有者のシナリオを、完了にする、または未完了に戻す。

        done が True なら `done_at` に現在時刻を入れる。既に入っているときは上書きせず、
        最初に完了にした時刻を残す。これにより、同じ操作を繰り返しても結果が変わらない。
        done が False なら `done_at` を null に戻す。シナリオの `status`(proposed か
        accepted か)は見ない。確認済みかどうかと、済ませたかどうかは独立している。

        Args:
            user_id: 所有者。別ユーザーの行は更新しない。
            capture_id: Capture の id。シナリオは Capture と同じ id で 1 行まで。
            done: True なら完了にする。False なら未完了に戻す。

        Returns:
            シナリオの行があれば True。既に同じ状態でも True を返す。行が無い、または
            別ユーザーの行なら False。
        """

        done_at = func.coalesce(CaptureScenarioModel.done_at, func.now()) if done else None
        stmt = (
            update(CaptureScenarioModel)
            .where(
                CaptureScenarioModel.capture_id == capture_id,
                CaptureScenarioModel.user_id == user_id,
            )
            .values(done_at=done_at, updated_at=func.now())
            .returning(CaptureScenarioModel.capture_id)
        )
        return await self._session.scalar(stmt) is not None

    async def accept_capture_scenario(self, user_id: UUID, *, capture_id: UUID) -> bool:
        """所有者の proposed のシナリオを、accepted にする。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。

        Returns:
            更新したら True。無い、別ユーザーの行、または proposed でなければ False。
        """

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
        """所有者の embedding が、この本文と同じ内容から作られているか確かめる。

        本文の sha256 を、保存済みの `content_hash` と比べる。同じなら、
        embedding を作り直す必要がない。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。
            text: 比べる本文。完了更新が hash を求める本文と同じものを渡す。

        Returns:
            同じ内容の embedding があれば True。
        """

        stmt = select(CaptureEmbeddingModel).where(
            CaptureEmbeddingModel.capture_id == capture_id,
            CaptureEmbeddingModel.user_id == user_id,
            CaptureEmbeddingModel.content_hash == hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        return await self._session.scalar(stmt) is not None


def _to_capture(row: CaptureModel, scenario_row: CaptureScenarioModel | None = None) -> Capture:
    """ORM の行を、ドメインの Capture に直す。

    Args:
        row: Capture の行。
        scenario_row: 付けるシナリオの行。無ければ None。

    Returns:
        scenario_row があれば、シナリオ付きの Capture。
    """

    scenario = None
    if scenario_row is not None:
        scenario = CaptureScenario(
            route=scenario_row.route,
            status=scenario_row.status,
            title=scenario_row.title,
            amount=scenario_row.amount,
            remind_text=scenario_row.remind_text,
            policy_version=scenario_row.policy_version,
            due_at=scenario_row.due_at,
            done_at=scenario_row.done_at,
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


def _to_embedding(row: CaptureEmbeddingModel | None = None) -> Embedding | None:
    """ORM の embedding の行を、ドメインの Embedding に直す。

    Args:
        row: embedding の行。外部結合で行が無いときは None。

    Returns:
        Embedding。row が None なら None。
    """

    if row is None:
        return None
    return Embedding(
        vector=tuple(row.embedding),
        model=row.embedding_model,
        dimensions=row.embedding_dimensions,
        version=row.embedding_version,
    )
