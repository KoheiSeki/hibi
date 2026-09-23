import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import HTTPExceptionHandler

from hibi.api.problem_details import FieldProblem, ProblemDetails
from hibi.core.errors import ApplicationError

logger = logging.getLogger(__name__)
PROBLEM_BASE = "https://api.hibi.example/problems"


def _request_id(request: Request) -> str:
    return request.state.request_id


def _response(problem: ProblemDetails) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(by_alias=True, exclude_none=True),
        media_type="application/problem+json",
    )


async def handle_application_error(request: Request, error: ApplicationError) -> JSONResponse:
    return _response(
        ProblemDetails(
            type=f"{PROBLEM_BASE}/{error.problem_type}",
            title=error.title,
            status=error.status,
            detail=error.detail,
            instance=request.url.path,
            request_id=_request_id(request),
        )
    )


async def handle_request_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    fields = []
    for item in error.errors():
        location = [str(part) for part in item["loc"] if part not in {"body", "query", "path"}]
        fields.append(
            FieldProblem(
                pointer="/" + "/".join(location), code=str(item["type"]), detail=str(item["msg"])
            )
        )
    return _response(
        ProblemDetails(
            type=f"{PROBLEM_BASE}/validation-error",
            title="Request validation failed",
            status=422,
            detail="One or more fields are invalid.",
            instance=request.url.path,
            request_id=_request_id(request),
            errors=fields,
        )
    )


async def handle_http_exception(request: Request, error: StarletteHTTPException) -> JSONResponse:
    title = "Not found" if error.status_code == 404 else "HTTP error"
    return _response(
        ProblemDetails(
            type=f"{PROBLEM_BASE}/http-error",
            title=title,
            status=error.status_code,
            detail=title,
            instance=request.url.path,
            request_id=_request_id(request),
        )
    )


async def handle_unexpected_exception(request: Request, error: Exception) -> JSONResponse:
    logger.exception("unexpected request failure", extra={"requestId": _request_id(request)})
    return _response(
        ProblemDetails(
            type=f"{PROBLEM_BASE}/internal-error",
            title="Internal server error",
            status=500,
            detail="An unexpected error occurred.",
            instance=request.url.path,
            request_id=_request_id(request),
        )
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        ApplicationError, cast(HTTPExceptionHandler, handle_application_error)
    )
    app.add_exception_handler(
        RequestValidationError, cast(HTTPExceptionHandler, handle_request_validation_error)
    )
    app.add_exception_handler(
        StarletteHTTPException, cast(HTTPExceptionHandler, handle_http_exception)
    )
    app.add_exception_handler(Exception, handle_unexpected_exception)
