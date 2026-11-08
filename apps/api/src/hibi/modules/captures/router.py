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
    Capture,
    CaptureScenario,
    CaptureSearchMode,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    UpdateCaptureCommand,
)

router = APIRouter(prefix="/captures", tags=["captures"])


def _get_capture_service(
    session: AsyncSession = Depends(get_session),
) -> CaptureService:
    repository = CaptureRepository(session=session)
    return CaptureService(
        session=session,
        repository=repository,
        classifier=build_capture_classifier(),
        generator=build_clarification_generator(),
        embedder=build_text_embedder(),
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
    capture = await service.accept_capture_scenario(principal.user_id, capture_id)
    response.headers["Location"] = f"/api/v1/captures/{capture.id}"
    return ApiResponse(data=_to_capture_response(capture))


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
    """
    完了した記録を、自分の分だけ検索する。

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
    await service.delete_capture(principal.user_id, capture_id)


def _to_capture_response(capture: Capture) -> CaptureResponse:
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
    if scenario is None:
        return None
    return ScenarioResponse(
        route=scenario.route,
        status=scenario.status,
        title=scenario.title,
        amount=scenario.amount,
        remind_text=scenario.remind_text,
        policy_version=scenario.policy_version,
    )
