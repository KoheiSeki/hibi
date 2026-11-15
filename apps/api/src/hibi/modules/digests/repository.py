from datetime import date
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.captures.models import OutboxModel
from hibi.modules.digests.models import DigestReportModel
from hibi.modules.digests.types import (
    DIGEST_AGGREGATE_TYPE,
    DIGEST_GENERATION_REQUESTED,
    DIGEST_STATUS_FAILED,
    DIGEST_STATUS_PENDING,
    DIGEST_STATUS_READY,
    DigestReport,
)


class DigestRepository:
    """ダイジェストと週次レビューの永続化。

    行の作成は `claim_report` の 1 回の INSERT で決める。同じ `(user_id, kind, period_start)` を
    複数の cron や worker が同時に作ろうとしても、入れられるのは 1 つだけで、その処理だけが
    中身を作る。状態の更新(`complete_report`、`fail_report`)は、`pending` からの遷移だけを
    受け付けるので、job が重複して走っても、`ready` や `failed` の行は書き換わらない。

    トランザクションは持たない。commit は呼び出し側(service や job)が行う。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def claim_report(
        self,
        *,
        report_id: UUID,
        user_id: UUID,
        kind: str,
        period_start: date,
        timezone: str,
        content_version: str,
        outbox_id: UUID,
    ) -> bool:
        """同じ期間の行が無ければ `pending` で作り、生成を依頼する outbox も足す。

        `INSERT ... ON CONFLICT DO NOTHING` で、`(user_id, kind, period_start)` の行を 1 件に保つ。
        入れられたときだけ outbox を足すので、cron を何度回しても、同時に回しても、
        job の依頼は期間ごとに 1 回になる。既に行があるときは、状態にかかわらず、何も変えず、
        outbox も足さない。止まった `pending` の再投入は、この関数ではなく別の回復の処理が行う。

        Args:
            report_id: 新しい行の id。アプリが `uuid7` で発行する。衝突したときは使われない。
            user_id: 所有者。
            kind: daily か weekly。それ以外は DB の check で `IntegrityError` になる。
            period_start: ユーザーの暦日。daily はその日、weekly は週の月曜。
            timezone: 期間の決定に使った IANA 名。
            content_version: 中身の形の版。
            outbox_id: outbox の id。job の重複防止の id に使われる。

        Returns:
            行を作ったら True。既にあって、何もしなかったら False。
        """

        stmt = (
            pg_insert(DigestReportModel)
            .values(
                id=report_id,
                user_id=user_id,
                kind=kind,
                period_start=period_start,
                timezone=timezone,
                status=DIGEST_STATUS_PENDING,
                content_version=content_version,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "kind", "period_start"])
            .returning(DigestReportModel.id)
        )
        inserted_id = await self._session.scalar(stmt)
        if inserted_id is None:
            return False

        self._session.add(
            OutboxModel(
                id=outbox_id,
                user_id=user_id,
                aggregate_type=DIGEST_AGGREGATE_TYPE,
                aggregate_id=report_id,
                event_type=DIGEST_GENERATION_REQUESTED,
                processing_generation=1,
            )
        )
        await self._session.flush()
        return True

    async def get_report(self, report_id: UUID) -> DigestReport | None:
        """id で行を 1 件読む。

        所有者の条件を持たない。job が `report_id` だけを受け取って中身を作る、内部の読み出し用。
        API から呼ぶ読み出しは、`user_id` を条件に含める別のメソッドを使う。

        Args:
            report_id: 読む行の id。

        Returns:
            行。無ければ None。
        """

        stmt = (
            select(DigestReportModel)
            .where(DigestReportModel.id == report_id)
            .execution_options(populate_existing=True)
        )
        row = await self._session.scalar(stmt)
        if row is None:
            return None
        return _to_digest_report(row)

    async def complete_report(
        self, report_id: UUID, *, content: dict[str, object], summary_model: str | None
    ) -> bool:
        """`pending` の行に中身を入れて `ready` にする。

        `UPDATE ... WHERE id = ... AND status = 'pending'` の 1 回で遷移させる。`pending` でない行は
        更新せず False を返すので、arq の at-least-once で job が重複して走っても、`ready` の
        中身は最初に入れたものから変わらない。`failed` の行も `ready` に戻らない。再実行は
        retry で `pending` に戻してから行う。`ready` と `content` の有無は DB の check で
        一致させているので、`status` と `content` は同じ文で更新する。

        Args:
            report_id: 完了にする行の id。
            content: ダイジェストの中身。`content_version` に合う形の JSON。
            summary_model: 週次レビューの要約に使ったモデル名。要約を使わない daily は None。

        Returns:
            `pending` から `ready` にしたら True。
            既に `ready` か `failed` で、何もしなかったら False。
        """

        stmt = (
            update(DigestReportModel)
            .where(
                DigestReportModel.id == report_id,
                DigestReportModel.status == DIGEST_STATUS_PENDING,
            )
            .values(
                status=DIGEST_STATUS_READY,
                content=content,
                summary_model=summary_model,
                generated_at=func.now(),
                updated_at=func.now(),
            )
            .returning(DigestReportModel.id)
        )
        return await self._session.scalar(stmt) is not None

    async def fail_report(self, report_id: UUID, *, error_code: str) -> bool:
        """`pending` の行を `failed` にして、理由を残す。

        `UPDATE ... WHERE id = ... AND status = 'pending'` の 1 回で遷移させる。`complete_report`
        と対になる。`ready` の行は更新せず False を返すので、重複して走った job や、遅れて
        届いた失敗が、既に作れた中身を `failed` に書き換えることはない。`failed` の行にも
        もう一度書かないので、最初の理由が残る。`failed` から戻すのは retry の責務で、
        `pending` に戻してから job が走り直す。

        Args:
            report_id: 失敗にする行の id。
            error_code: 失敗の理由を表す短い識別子。timeout や 429 などの種類で、例外のメッセージや
                ユーザーの内容は入れない。

        Returns:
            `pending` から `failed` にしたら True。
            既に `ready` か `failed` で、何もしなかったら False。
        """

        stmt = (
            update(DigestReportModel)
            .where(
                DigestReportModel.id == report_id,
                DigestReportModel.status == DIGEST_STATUS_PENDING,
            )
            .values(
                status=DIGEST_STATUS_FAILED,
                error_code=error_code,
                updated_at=func.now(),
            )
            .returning(DigestReportModel.id)
        )
        return await self._session.scalar(stmt) is not None


def _to_digest_report(row: DigestReportModel) -> DigestReport:
    """ORM の行を、session の外でも読めるドメインの型に写す。"""

    return DigestReport(
        id=row.id,
        user_id=row.user_id,
        kind=row.kind,
        period_start=row.period_start,
        timezone=row.timezone,
        status=row.status,
        content=row.content,
        content_version=row.content_version,
        summary_model=row.summary_model,
        error_code=row.error_code,
        generated_at=row.generated_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
