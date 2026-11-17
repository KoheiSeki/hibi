from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.captures.models import CaptureModel, CaptureScenarioModel, OutboxModel
from hibi.modules.digests.models import DigestReportModel
from hibi.modules.digests.types import (
    DIGEST_AGGREGATE_TYPE,
    DIGEST_GENERATION_REQUESTED,
    DIGEST_STATUS_FAILED,
    DIGEST_STATUS_PENDING,
    DIGEST_STATUS_READY,
    ActiveUser,
    DigestReport,
)
from hibi.modules.profiles.models import ProfileModel


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

    async def list_active_users(self, *, active_since: datetime, limit: int) -> list[ActiveUser]:
        """直近に Capture がある利用者と、その timezone を読む。

        cron が 15 分ごとに、ダイジェストを作る対象を探すのに使う。`active_since` 以降に
        Capture を作った利用者だけを返すので、休眠中の利用者に空のダイジェストを作り続けない。
        1 人は 1 回だけ返す。Capture の数にかかわらず重複しない。

        timezone はプロフィールから読む。Capture は、プロフィールが無い利用者には作れない
        (外部キー)ので、プロフィールが無い利用者は、ここに現れない。名前の検証はしない。
        不正な名前は、日付を決める側が UTC として扱う。

        並びは `user_id` の昇順で固定する。`limit` を超える利用者がいると、後ろの利用者が
        毎回対象から外れて、いつまでもダイジェストが作られない。`limit` は、1 回の cron が
        抱える量の上限で、全利用者を覆う上限ではない。利用者が増えたら、読み方を変える。

        Args:
            active_since: この時刻以降に Capture がある利用者を対象にする。aware な datetime。
            limit: 返す利用者の最大数。

        Returns:
            利用者の id と timezone。該当が無ければ空のリスト。
        """

        stmt = (
            select(CaptureModel.user_id, ProfileModel.timezone)
            .join(ProfileModel, CaptureModel.user_id == ProfileModel.user_id)
            .where(CaptureModel.created_at >= active_since)
            .group_by(CaptureModel.user_id, ProfileModel.timezone)
            .order_by(CaptureModel.user_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [
            ActiveUser(user_id=user_id, timezone=timezone) for user_id, timezone in result.all()
        ]

    async def count_done_between(self, user_id: UUID, *, start: datetime, end: datetime) -> int:
        """所有者が、期間の中で完了にしたシナリオの数を返す。

        日次ダイジェストの「昨日、完了にした件数」に使う。`done_at` が `start` 以上で、
        `end` より前のものを数える。期間は半開区間で、`end` ちょうどに完了にしたものは、
        次の期間の分になる。そのため、昨日の終わりと今日の始まりが同じ時刻でも、二重に数えない。
        暦日の境界は、夏時間の日を含むため、この関数では決めない。呼び出し側が、ユーザーの
        timezone で求めた UTC の時刻を渡す。

        完了を未完了に戻したシナリオは `done_at` が null になるので、数えない。Capture を
        削除すると、シナリオも消えるので、その完了も数えない。

        Args:
            user_id: 所有者。別ユーザーのシナリオは数えない。
            start: 期間の始まり。この時刻を含む。UTC の aware な datetime。
            end: 期間の終わり。この時刻を含まない。UTC の aware な datetime。

        Returns:
            期間に完了にしたシナリオの数。無ければ 0。
        """

        stmt = (
            select(func.count())
            .select_from(CaptureScenarioModel)
            .where(
                CaptureScenarioModel.user_id == user_id,
                CaptureScenarioModel.done_at >= start,
                CaptureScenarioModel.done_at < end,
            )
        )
        return await self._session.scalar(stmt) or 0


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
