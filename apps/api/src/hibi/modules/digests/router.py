from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.factory import build_review_summarizer
from hibi.api.dependencies import get_principal
from hibi.api.openapi import problem_responses
from hibi.api.schemas import ApiResponse
from hibi.auth.principal import Principal
from hibi.db import get_session
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.digests.constants import (
    DIGEST_LIST_DEFAULT_LIMIT,
    DIGEST_LIST_MAX_LIMIT,
    DigestKind,
)
from hibi.modules.digests.repository import DigestRepository
from hibi.modules.digests.schemas import DigestReportResponse
from hibi.modules.digests.service import DigestService
from hibi.modules.digests.types import (
    DigestReport,
    ListDigestReportsQuery,
)

router = APIRouter(prefix="/digest-reports", tags=["digest-reports"])


def _get_digest_service(session: AsyncSession = Depends(get_session)) -> DigestService:
    """リクエストごとに、DigestService を組み立てる。

    一覧と retry は、要約を作らない。それでも `summarizer` を渡すのは、service が
    1 つの型で、job と同じ組み立て方にそろえるため。`build_review_summarizer` は
    client を作るだけで、network に繋がないので、リクエストごとに作っても軽い。
    テストは、この関数を `dependency_overrides` で fake の service に差し替える。

    Args:
        session: リクエストの DB セッション。2 つの repository が共有する。

    Returns:
        設定に合わせて要約の実装を選んだ DigestService。
    """

    digests = DigestRepository(session=session)
    captures = CaptureRepository(session=session)
    return DigestService(digests=digests, captures=captures, summarizer=build_review_summarizer())


@router.get(
    "",
    operation_id="listDigestReports",
    response_model=ApiResponse[list[DigestReportResponse]],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def list_digest_reports(
    kind: Annotated[DigestKind | None, Query()] = None,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    limit: Annotated[int, Query(ge=1, le=DIGEST_LIST_MAX_LIMIT)] = DIGEST_LIST_DEFAULT_LIMIT,
    principal: Principal = Depends(get_principal),
    service: DigestService = Depends(_get_digest_service),
):
    """自分の朝のダイジェストと週次レビューを、期間の日付の新しい順に返す。

    kind は daily か weekly で、未指定なら両方。fromDate は periodStart の下限で、
    その日を含む(YYYY-MM-DD)。作った日ではなく、期間の日付で絞る。limit は 1 以上
    30 以下で、未指定は 7。範囲外や不正な値は 422。

    作っている途中(pending)と、失敗した行(failed)も返す。対象が無ければ空の配列を
    返し、404 にはしない。
    """

    query = ListDigestReportsQuery(
        user_id=principal.user_id, kind=kind, from_date=from_date, limit=limit
    )
    reports = await service.list_reports(query)
    return ApiResponse(data=[_to_digest_report_response(report) for report in reports])


@router.post(
    "/{report_id}/retry",
    operation_id="retryDigestReport",
    response_model=ApiResponse[DigestReportResponse],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def retry_digest_report(
    report_id: UUID,
    principal: Principal = Depends(get_principal),
    service: DigestService = Depends(_get_digest_service),
):
    """失敗したダイジェストか週次レビューを、もう一度作るよう予約する。

    status が failed の行だけを pending に戻し、戻した行を 202 で返す。このとき
    content と errorCode は null。中身は後で作られるので、ready になったかは、
    一覧(listDigestReports)を読み直して確かめる。

    failed でない行(pending か ready)は 409。同じ行に retry が続けて届いたときも、
    2 回目からは pending なので 409 になる。自分の行でない、または無ければ 404。
    reportId が UUID でなければ 422。
    """

    report = await service.retry_report(principal.user_id, report_id=report_id)
    return ApiResponse(data=_to_digest_report_response(report))


def _to_digest_report_response(report: DigestReport) -> DigestReportResponse:
    """ドメインの DigestReport を、API のレスポンスに直す。

    `user_id`、`summary_model`、`created_at`、`updated_at` は出さない。所有者は
    応答の受け手そのもので、モデル名と作成、更新の時刻は、画面で使わない内部の
    情報のため。`content` は、保存したときに camelCase の JSON にしてあるので、
    形を変えずにそのまま渡す。

    Args:
        report: 所有者の行。どの状態の行でもよい。

    Returns:
        API の応答の 1 件。`content` と `generatedAt` は ready のときだけ、
        `errorCode` は failed のときだけ入る。
    """

    return DigestReportResponse(
        id=report.id,
        kind=report.kind,
        period_start=report.period_start,
        timezone=report.timezone,
        status=report.status,
        content=report.content,
        content_version=report.content_version,
        error_code=report.error_code,
        generated_at=report.generated_at,
    )
