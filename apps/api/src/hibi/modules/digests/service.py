from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from uuid import UUID, uuid7

from hibi.ai.review_summary import ReviewSummarizer, WeeklyReviewInput, WeeklyStats
from hibi.core.timezone import local_day_start, utc_now
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.today import rank_today
from hibi.modules.digests.content import (
    DAILY_CONTENT_VERSION,
    DAILY_ITEM_LIMIT,
    EMPTY_WEEK_SUMMARY,
    WEEKLY_CONTENT_VERSION,
    DigestItem,
    build_daily_content,
    build_weekly_content,
    count_deadlines,
    normalize_summary,
)
from hibi.modules.digests.errors import DigestReportNotFoundError, DigestReportNotRetryableError
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.schedule import daily_period_start, weekly_period_start
from hibi.modules.digests.types import (
    DIGEST_KIND_DAILY,
    DIGEST_KIND_WEEKLY,
    DIGEST_STATUS_PENDING,
    ActiveUser,
    DigestReport,
    ListDigestReportsQuery,
)

_ACTIVE_USER_LIMIT = 1000
_ACTIVE_WINDOW_DAYS = 14

# 週次レビューの要約に渡す、完了したシナリオの題の上限。要約は 500 文字なので、
# これより多くの題を渡しても、要約は良くならず、プロンプトが長くなるだけ
_WEEKLY_DONE_TITLE_LIMIT = 20


class DigestService:
    """ダイジェストと週次レビューを、作る時刻の判定から中身の組み立てまで担当する。

    作る時刻の判定は `schedule.py`、中身の組み立ては `content.py` の純粋関数に任せ、
    この service は、repository から読んだ値を渡して、結果を保存する順序だけを持つ。
    優先度の計算は変えず、Today と同じ `rank_today` を使う。

    トランザクションは持たない。commit は呼び出し側(job の `session_scope`)が行う。
    """

    def __init__(
        self,
        digests: DigestRepository,
        captures: CaptureRepository,
        summarizer: ReviewSummarizer,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        """サービスが使う依存を受け取って保持する。

        Args:
            digests: ダイジェストの永続化。
            captures: Today の候補と、Capture の読み出し。
            clock: 現在時刻の取得元。作る時刻の判定と、順位付けの基準になる。
                テストで固定時刻を差し込めるよう、引数にしている。
        """

        self._digests = digests
        self._captures = captures
        self._summarizer = summarizer
        self._clock = clock

    async def list_reports(self, query: ListDigestReportsQuery) -> list[DigestReport]:
        """所有者のダイジェストと週次レビューを、期間の日付の新しい順に返す。

        条件はそのまま repository に渡し、ここでは加工しない。値の範囲は router が
        検証済みで、所有者の条件は `query.user_id` で必ず付く。`pending` と `failed` の
        行も、そのまま返す。画面が、作っている途中と、失敗の表示を出すため。

        Args:
            query: 所有者、種類、期間の日付の下限、最大件数。

        Returns:
            新しい順の行。無ければ空のリスト。
        """

        return await self._digests.list_reports(
            query.user_id, kind=query.kind, from_date=query.from_date, limit=query.limit
        )

    async def schedule_due_reports(self) -> int:
        """今が作る時刻の利用者に、足りないダイジェストの行を作り、生成を予約する。

        cron が 15 分ごとに呼ぶ。直近 14 日以内に Capture がある利用者を読み、利用者ごとに、
        ユーザーの timezone で、daily と weekly が今作る時刻かを判定する。作る時刻なら、
        `claim_report` で `pending` の行と outbox を同じ transaction で足す。ユーザーごとの
        予定は持たない。実行のたびに、同じ判定を繰り返す。

        同じ期間の行が既にあれば、`claim_report` が何もしないので、cron を何度回しても、
        複数の worker が重なっても、行と outbox は 1 件のまま。止まっていた間の日は作らない。
        7 時を過ぎた、その日の分だけを作る。

        中身はここでは作らない。outbox を経由して `generate_digest_report_job` が作る。
        1 人の利用者の claim が例外になると、そこで止まる。残りは、次の 15 分後の cron が
        作り直す。

        Returns:
            この呼び出しで、新しく行を作った数。既にあって何もしなかった行は数えない。
        """

        now = self._clock()
        active_since = now - timedelta(days=_ACTIVE_WINDOW_DAYS)
        active_users = await self._digests.list_active_users(
            active_since=active_since, limit=_ACTIVE_USER_LIMIT
        )

        claimed_count = 0
        for user in active_users:
            daily_start = daily_period_start(now, timezone=user.timezone)
            if daily_start is not None:
                claimed_count += await self._claim(
                    user,
                    kind=DIGEST_KIND_DAILY,
                    period_start=daily_start,
                    content_version=DAILY_CONTENT_VERSION,
                )

            weekly_start = weekly_period_start(now, timezone=user.timezone)
            if weekly_start is not None:
                claimed_count += await self._claim(
                    user,
                    kind=DIGEST_KIND_WEEKLY,
                    period_start=weekly_start,
                    content_version=WEEKLY_CONTENT_VERSION,
                )

        return claimed_count

    async def generate_report(self, report_id: UUID) -> None:
        """`pending` の行の中身を作って、`ready` にする。

        outbox を経由して、`generate_digest_report_job` が呼ぶ。行が無いか、`pending` で
        なければ、何もせず終える。job は at-least-once で、同じ行に重複して届くことがあり、
        先に別の job が `ready` か `failed` にした行を、書き換えないため。読んだあとに別の job が
        先に完了させたときも、`complete_report` が False を返すだけで、例外にはしない。

        daily は、LLM を使わず、決定論的に作る。Today と同じ候補を `rank_today` で
        `DAILY_ITEM_LIMIT` 件に絞り、期限の件数と、昨日の完了数を数えて、内容にする。
        期限と順位は、現在時刻と、行に記録した timezone で決める。昨日は、行の期間の
        日付の前日で、作るのが遅れても、その行の日の前日を数える。順位付けのあとに
        消えた Capture は、黙って外す。内容には、題と期限だけを入れ、本文は入れない。

        ここでは失敗を確定しない。例外は、そのまま呼び出し側へ上げる。再試行と、最終試行での
        `failed` への更新は、job が行う。

        Args:
            report_id: 中身を作る行の id。

        Raises:
            Exception: 読み出しや組み立てに失敗した。job の retry に任せる。
        """

        report = await self._digests.get_report(report_id)
        if report is None or report.status != DIGEST_STATUS_PENDING:
            return

        if report.kind == DIGEST_KIND_DAILY:
            content = await self._build_daily_content(report)
            await self._digests.complete_report(report_id, content=content, summary_model=None)
        elif report.kind == DIGEST_KIND_WEEKLY:
            content, summary_model = await self._build_weekly_content(report)
            await self._digests.complete_report(
                report_id=report.id, content=content, summary_model=summary_model
            )

    async def retry_report(self, user_id: UUID, *, report_id: UUID) -> DigestReport:
        """failed の行を pending に戻し、中身の生成をもう一度予約する。

        画面の「もう一度作る」が使う。戻す判断は、repository の 1 回の条件つき更新に
        任せるので、retry が続けて届いても、生成の予約(outbox)は 1 件しか増えない。
        outbox の id は、ここで新しく発行する。

        戻せなかったときだけ、行を読み直して、理由を分ける。行が無いときと、別ユーザーの
        行のときは、どちらも `DigestReportNotFoundError` にする。他人の行が存在することを、
        応答から推測させないため。それ以外(pending か ready)は、`DigestReportNotRetryableError`
        にする。読み直しの前に、別の要求が戻していた場合も、pending なので 409 になる。

        Args:
            user_id: 検証済みの所有者。
            report_id: 戻す行の id。

        Returns:
            pending に戻した行。`content` と `error_code` は None。

        Raises:
            DigestReportNotFoundError: 行が無い、または別ユーザーの行。
            DigestReportNotRetryableError: 行が failed でない。
        """

        report = await self._digests.requeue_failed_report(
            user_id, report_id=report_id, outbox_id=uuid7()
        )
        if report is not None:
            return report

        current = await self._digests.get_report(report_id)
        if current is None or current.user_id != user_id:
            raise DigestReportNotFoundError(report_id)
        raise DigestReportNotRetryableError()

    async def _build_daily_content(self, report: DigestReport) -> dict[str, object]:
        """日次ダイジェストの中身を、Today の候補と昨日の完了数から組み立てる。

        候補は 1 回だけ読み、順位付けと期限の件数の両方に渡す。2 回読むと、間に状態が
        変わったとき、`items` と件数が食い違うため。現在時刻も 1 回だけ読む。

        Args:
            report: 中身を作る行。所有者、timezone、期間の日付を使う。

        Returns:
            `build_daily_content` が作る、`jsonb` に保存できる辞書。
        """

        now = self._clock()
        candidates = await self._captures.list_open_scenario_candidates(report.user_id)
        ranked_ids = rank_today(
            candidates, now=now, timezone=report.timezone, limit=DAILY_ITEM_LIMIT
        )
        items = await self._load_items(report.user_id, ranked_ids)
        deadline_counts = count_deadlines(candidates, now=now, timezone=report.timezone)

        # 昨日は、now ではなく行の期間の日付の前日。作るのが遅れても、その日の前日を数える
        yesterday = report.period_start - timedelta(days=1)
        done_yesterday_count = await self._digests.count_done_between(
            report.user_id,
            start=local_day_start(yesterday, timezone=report.timezone),
            end=local_day_start(report.period_start, timezone=report.timezone),
        )
        return build_daily_content(
            items=items,
            deadline_counts=deadline_counts,
            done_yesterday_count=done_yesterday_count,
        )

    async def _build_weekly_content(
        self, report: DigestReport
    ) -> tuple[dict[str, object], str | None]:
        """週次レビューの中身を、先週の集計と LLM の要約から組み立てる。

        先週は、行の期間の日付(月曜)の 0 時から、翌週の月曜の 0 時までで、行に記録した
        timezone で決める。暦日から求めるので、夏時間の週は 167 時間や 169 時間になる。
        記録の数、完了の数、完了の題は、この範囲で読む。未完了と期限超過の数は、今の
        時点の候補から数える。先週の終わりの時点の状態は、記録が無く求められないため。

        先週に Capture が 1 件も無ければ、LLM を呼ばず、`EMPTY_WEEK_SUMMARY` にする。
        要約の材料が無いので、呼んでも意味がないため。それ以外は、集計と完了の題だけを
        渡して、LLM を 1 回呼ぶ。本文の項目は渡さない。返った要約は `normalize_summary` を
        通し、空や長すぎるときは、再試行せず定型文にする。

        Args:
            report: 中身を作る行。所有者、timezone、期間の日付を使う。

        Returns:
            `build_weekly_content` が作る辞書と、`summary_model` に記録するモデル名の組。
            LLM を呼ばなかった週は、モデル名が None。

        Raises:
            ReviewProviderError: LLM の一時的な障害。握りつぶさず、job の retry に任せる。
        """

        week_start = local_day_start(report.period_start, timezone=report.timezone)
        week_end = local_day_start(
            report.period_start + timedelta(days=7), timezone=report.timezone
        )
        captured_count = await self._digests.count_captured_between(
            report.user_id, start=week_start, end=week_end
        )
        done_count = await self._digests.count_done_between(
            report.user_id, start=week_start, end=week_end
        )
        candidates = await self._captures.list_open_scenario_candidates(report.user_id)
        overdue_count = count_deadlines(
            candidates, now=self._clock(), timezone=report.timezone
        ).overdue_count
        done_titles = await self._digests.list_done_titles_between(
            report.user_id, start=week_start, end=week_end, limit=_WEEKLY_DONE_TITLE_LIMIT
        )
        stats = WeeklyStats(
            captured_count=captured_count,
            done_count=done_count,
            open_count=len(candidates),
            overdue_count=overdue_count,
        )
        if stats.captured_count == 0:
            return build_weekly_content(stats=stats, summary=EMPTY_WEEK_SUMMARY), None
        review = WeeklyReviewInput(stats=stats, done_titles=done_titles)
        summary = await self._summarizer.summarize_week(review)
        return build_weekly_content(
            stats=stats, summary=normalize_summary(summary)
        ), self._summarizer.model_name

    async def _load_items(self, user_id: UUID, ranked_ids: Sequence[UUID]) -> list[DigestItem]:
        """順位付けで選んだ id から、ダイジェストの行(題と期限)を順位どおりに作る。

        `list_captures_by_ids` は順序を保証しないので、`ranked_ids` の順に並べ直す。
        順位付けのあとに削除された Capture と、シナリオが無い Capture は、黙って外す。

        Args:
            user_id: 所有者。
            ranked_ids: 優先度の高い順の Capture の id。空なら DB を読まない。

        Returns:
            順位どおりの DigestItem。外した分だけ、`ranked_ids` より短くなることがある。
        """

        if not ranked_ids:
            return []

        captures = await self._captures.list_captures_by_ids(user_id, capture_ids=ranked_ids)
        by_id = {capture.id: capture for capture in captures}
        items: list[DigestItem] = []
        for capture_id in ranked_ids:
            capture = by_id.get(capture_id)
            if capture is None or capture.scenario is None:
                continue
            items.append(
                DigestItem(
                    capture_id=capture.id,
                    title=capture.scenario.title,
                    due_at=capture.scenario.due_at,
                )
            )
        return items

    async def _claim(
        self, user: ActiveUser, *, kind: str, period_start: date, content_version: str
    ) -> bool:
        """利用者の 1 つの期間について、`pending` の行と outbox の予約を試みる。

        daily と weekly の違いは、種類と期間と内容の版だけなので、呼び出しをここにまとめる。
        行の id と outbox の id は、呼ぶたびに別の `uuid7` を新しく発行する。行が既にあって
        入らなかったときは、この id は使われずに捨てられる。timezone は、利用者のプロフィールの
        値をそのまま記録する。

        Args:
            user: 対象の利用者。id と timezone を使う。
            kind: daily か weekly。
            period_start: ユーザーの暦日。daily はその日、weekly は週の月曜。
            content_version: 中身の形の版。

        Returns:
            行を新しく作ったら True。既にあって何もしなかったら False。
        """

        return await self._digests.claim_report(
            report_id=uuid7(),
            user_id=user.user_id,
            kind=kind,
            period_start=period_start,
            timezone=user.timezone,
            content_version=content_version,
            outbox_id=uuid7(),
        )
