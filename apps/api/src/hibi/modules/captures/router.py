from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.classifier_factory import (
    build_capture_classifier,
    build_clarification_generator,
    build_text_embedder,
)
from hibi.api.dependencies import get_principal
from hibi.api.openapi import problem_responses
from hibi.api.schemas import ApiResponse, ApiResponseWithMeta, CursorMeta
from hibi.auth.principal import Principal
from hibi.db.session import get_session
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.schemas import (
    CaptureResponse,
    CreateCaptureRequest,
    ScenarioResponse,
    UpdateCaptureRequest,
)
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    CAPTURE_SEARCH_MODE_KEYWORD,
    TODAY_DEFAULT_LIMIT,
    TODAY_MAX_LIMIT,
    Capture,
    CaptureScenario,
    CaptureSearchMode,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    TodayCapturesQuery,
    UpdateCaptureCommand,
)
from hibi.modules.profiles.repository import ProfileRepository

router = APIRouter(prefix="/captures", tags=["captures"])


def _get_capture_service(
    session: AsyncSession = Depends(get_session),
) -> CaptureService:
    """リクエストごとに、CaptureService を組み立てる。

    Args:
        session: リクエストの DB セッション。repository と profiles が共有する。

    Returns:
        分類器、聞き返しの生成器、embedder を、設定に合わせて選んだ CaptureService。
    """

    repository = CaptureRepository(session=session)
    profile = ProfileRepository(session=session)
    return CaptureService(
        session=session,
        repository=repository,
        classifier=build_capture_classifier(),
        generator=build_clarification_generator(),
        embedder=build_text_embedder(),
        profiles=profile,
    )


@router.post(
    "",
    operation_id="createCapture",
    response_model=ApiResponse[CaptureResponse],
    responses={
        status.HTTP_200_OK: {"model": ApiResponse[CaptureResponse]},
        **problem_responses(
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_409_CONFLICT,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
        ),
    },
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_capture(
    body: CreateCaptureRequest,
    response: Response,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """記録を作り、AI による処理を予約する。

    処理は非同期で、作成直後の status は pending。処理が終わるまで、単体取得で
    status を確かめる。Idempotency-Key ヘッダーが必須で、同じキーと本文の再送は
    新しく作らず、既存の記録を 200 で返す。新規は 202。キーが無い、または形式が
    不正なら 400。同じキーで本文が違えば 409。本文は前後の空白を除いて 1 文字以上
    2000 文字以下で、違反は 422。
    """

    command = CreateCaptureCommand(
        user_id=principal.user_id,
        raw_text=body.raw_text,
        idempotency_key=idempotency_key,
    )
    result: CreateCaptureResult = await service.create_capture(command)

    response.status_code = status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
    response.headers["Location"] = f"/api/v1/captures/{result.capture.id}"
    return ApiResponse(data=_to_capture_response(result.capture))


@router.post(
    "/{capture_id}/retry",
    operation_id="retryCapture",
    response_model=ApiResponse[CaptureResponse],
    status_code=status.HTTP_202_ACCEPTED,
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def retry_capture(
    capture_id: UUID,
    response: Response,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """failed の記録を、もう一度処理に回す。

    処理の世代が 1 つ進み、status は pending に戻る。成功は 202。failed 以外の
    記録は 409。自分の記録でない、または無ければ 404。
    """

    capture = await service.retry_capture(principal.user_id, capture_id)
    response.headers["Location"] = f"/api/v1/captures/{capture.id}"
    return ApiResponse(data=_to_capture_response(capture))


@router.post(
    "/{capture_id}/scenario/accept",
    operation_id="acceptCaptureScenario",
    response_model=ApiResponse[CaptureResponse],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def accept_capture_scenario(
    capture_id: UUID,
    response: Response,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """提案されたシナリオを、確認して accepted にする。

    確認できるのは所有者だけで、proposed のシナリオに限る。成功は 200 で、更新後の
    記録を返す。自分の記録でない、またはシナリオが無ければ 404。確認済みなど、
    proposed でないシナリオは 409。
    """

    capture = await service.accept_capture_scenario(principal.user_id, capture_id)
    response.headers["Location"] = f"/api/v1/captures/{capture.id}"
    return ApiResponse(data=_to_capture_response(capture))


@router.post(
    "/{capture_id}/scenario/done",
    operation_id="markCaptureScenarioDone",
    response_model=ApiResponse[CaptureResponse],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def mark_capture_scenario_done(
    capture_id: UUID,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """記録のシナリオを、完了にする。

    今日やることから外れる。繰り返し呼んでも結果は同じで、200 を返す。完了にした
    時刻は、最初に呼んだときのものが残る。シナリオを確認済み(accepted)にして
    いなくても、完了にできる。成功は 200 で、更新後の記録を返す。自分の記録でない、
    記録が無い、またはシナリオが無ければ、理由を区別せず 404。
    """

    capture = await service.set_capture_scenario_done(principal.user_id, capture_id, done=True)
    return ApiResponse(data=_to_capture_response(capture))


@router.get(
    "/today",
    operation_id="listTodayCaptures",
    response_model=ApiResponse[list[CaptureResponse]],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def list_today_captures(
    limit: Annotated[int, Query(ge=1, le=TODAY_MAX_LIMIT)] = TODAY_DEFAULT_LIMIT,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """今日やることを、優先度の高い順に返す。

    自分の未完了のシナリオのうち、期限が今日までのものが対象。期限を過ぎたものも
    含む。今日の終わりは、プロフィールの timezone の暦日で決まる。緊急度が高い
    ものと、期限が近いものが上に来る。同じ優先度のときの順序は、毎回同じになる。

    limit は 1 以上 20 以下で、未指定は 5。範囲外は 422。対象が無ければ空の配列を
    返し、404 にはしない。
    """

    query = TodayCapturesQuery(user_id=principal.user_id, limit=limit)
    captures = await service.list_today_captures(query)
    return ApiResponse(data=[_to_capture_response(capture) for capture in captures])


@router.get(
    "/search",
    operation_id="searchCaptures",
    response_model=ApiResponse[list[CaptureResponse]],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def search_captures(
    q: str = Query(min_length=1, max_length=200),
    mode: Annotated[CaptureSearchMode, Query()] = CAPTURE_SEARCH_MODE_KEYWORD,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """完了した記録を、自分の分だけ検索する。

    mode=keyword は本文の語の重なり、mode=semantic は意味の近さで選ぶ。
    近い順に最大20件を返し、見つからなければ空配列を返す。
    """

    query = SearchCapturesQuery(user_id=principal.user_id, q=q, mode=mode)
    captures = await service.search_captures(query)
    return ApiResponse(data=[_to_capture_response(capture) for capture in captures])


@router.get(
    "/{capture_id}",
    operation_id="getCapture",
    response_model=ApiResponse[CaptureResponse],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def get_capture(
    capture_id: UUID,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """記録を 1 件取得する。シナリオと聞き返し文があれば、あわせて返す。

    処理中かどうかは status で分かる。自分の記録でない、または無ければ 404。
    """

    capture: Capture = await service.get_capture(principal.user_id, capture_id)
    return ApiResponse(data=_to_capture_response(capture))


@router.get(
    "",
    operation_id="listCaptures",
    response_model=ApiResponseWithMeta[list[CaptureResponse], CursorMeta],
    responses=problem_responses(
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def list_captures(
    limit: int = Query(default=20, ge=1, le=50),
    cursor: str | None = Query(default=None),
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """自分の記録を、新しい順に一覧で返す。

    limit は 1 以上 50 以下で、未指定は 20。続きは、前の応答の meta.nextCursor を
    cursor に渡して取得する。cursor が不正なら 400。
    """

    query = ListCapturesQuery(user_id=principal.user_id, limit=limit, cursor=cursor)
    page = await service.list_captures(query)

    meta = CursorMeta(next_cursor=page.next_cursor, has_next_page=page.has_next_page)
    return ApiResponseWithMeta(
        data=[_to_capture_response(capture) for capture in page.items], meta=meta
    )


@router.patch(
    "/{capture_id}",
    operation_id="updateCapture",
    response_model=ApiResponse[CaptureResponse],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def update_capture(
    capture_id: UUID,
    body: UpdateCaptureRequest,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """記録の本文を更新する。

    更新できるのは pending と failed の記録だけ。処理中と完了済みは 409。本文は
    前後の空白を除いて 1 文字以上 2000 文字以下で、違反は 422。自分の記録でない、
    または無ければ 404。
    """

    command = UpdateCaptureCommand(
        user_id=principal.user_id, capture_id=capture_id, raw_text=body.raw_text
    )
    capture: Capture = await service.update_capture(command)
    return ApiResponse(data=_to_capture_response(capture))


@router.delete(
    "/{capture_id}",
    operation_id="deleteCapture",
    response_model=None,
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_capture(
    capture_id: UUID,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """記録を削除する。

    シナリオと embedding も一緒に消える。成功は 204 で本文は無い。自分の記録でない、
    または無ければ 404。
    """

    await service.delete_capture(principal.user_id, capture_id)


@router.delete(
    "/{capture_id}/scenario/done",
    operation_id="unmarkCaptureScenarioDone",
    response_model=ApiResponse[CaptureResponse],
    responses=problem_responses(
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
)
async def unmark_capture_scenario_done(
    capture_id: UUID,
    principal: Principal = Depends(get_principal),
    service: CaptureService = Depends(_get_capture_service),
):
    """記録のシナリオを、未完了に戻す。

    完了にしていなくても呼べて、その場合も 200 を返す。戻した記録は、期限などの
    条件が合えば、今日やることに再び出る。成功は 200 で、更新後の記録を返す。本文は
    空にならず、204 ではない。自分の記録でない、記録が無い、またはシナリオが無ければ、
    理由を区別せず 404。
    """

    capture = await service.set_capture_scenario_done(principal.user_id, capture_id, done=False)
    return ApiResponse(data=_to_capture_response(capture))


def _to_capture_response(capture: Capture) -> CaptureResponse:
    """ドメインの Capture を、API のレスポンスに直す。

    Args:
        capture: シナリオ付きでもよい Capture。

    Returns:
        confidence を float にし、シナリオがあれば ScenarioResponse に直した結果。
    """

    return CaptureResponse(
        id=capture.id,
        raw_text=capture.raw_text,
        status=capture.status,
        created_at=capture.created_at,
        updated_at=capture.updated_at,
        category=capture.category,
        route=capture.route,
        urgency=capture.urgency,
        confidence=(float(capture.confidence) if capture.confidence is not None else None),
        policy_version=capture.policy_version,
        question_version=capture.question_version,
        processed_at=capture.processed_at,
        clarification_text=capture.clarification_text,
        scenario=_to_scenario_response(capture.scenario),
    )


def _to_scenario_response(scenario: CaptureScenario | None) -> ScenarioResponse | None:
    """ドメインの CaptureScenario を、API のレスポンスに直す。

    Args:
        scenario: シナリオ。無ければ None。

    Returns:
        ScenarioResponse。scenario が None なら None。
    """

    if scenario is None:
        return None
    return ScenarioResponse(
        route=scenario.route,
        status=scenario.status,
        title=scenario.title,
        amount=scenario.amount,
        remind_text=scenario.remind_text,
        policy_version=scenario.policy_version,
        due_at=scenario.due_at,
        done_at=scenario.done_at,
    )
