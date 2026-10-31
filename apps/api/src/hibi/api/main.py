from collections.abc import Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from hibi.api.dependencies import get_principal
from hibi.api.exception_handlers import register_exception_handlers
from hibi.api.openapi import ProblemDetailsFastAPI, problem_responses
from hibi.api.schemas import (
    ApiResponse,
    EchoRequest,
    EchoResponse,
    HealthResponse,
    ProtectedResourceResponse,
    UserResponse,
)
from hibi.auth.principal import Principal
from hibi.core.config import get_settings
from hibi.core.logging import configure_logging
from hibi.db.engine import dispose_engine
from hibi.modules.captures.router import router as captures_router
from hibi.modules.profiles.service import get_owned_resource

ResourceLookup = Callable[[UUID], str]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await dispose_engine()


def _default_resource_lookup(user_id: UUID) -> str:
    return f"resource-for-{user_id}"


def create_app(resource_lookup: ResourceLookup = _default_resource_lookup) -> FastAPI:
    app = ProblemDetailsFastAPI(title="Hibi API", version="0.1.0", lifespan=lifespan)
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "Idempotency-Key",
        ],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.get(
        "/api/v1/health",
        response_model=ApiResponse[HealthResponse],
        operation_id="getHealth",
        responses=problem_responses(500),
    )
    async def get_health() -> ApiResponse[HealthResponse]:
        return ApiResponse(data=HealthResponse(status="ok"))

    @app.post(
        "/api/v1/echo",
        response_model=ApiResponse[EchoResponse],
        operation_id="echoMessage",
        responses=problem_responses(422, 500),
    )
    async def echo_message(request: EchoRequest) -> ApiResponse[EchoResponse]:
        return ApiResponse(data=EchoResponse(message=request.message))

    @app.get(
        "/api/v1/me",
        response_model=ApiResponse[UserResponse],
        operation_id="getCurrentUser",
        responses=problem_responses(401, 500),
    )
    async def get_current_user(
        principal: Principal = Depends(get_principal),
    ) -> ApiResponse[UserResponse]:
        return ApiResponse(data=UserResponse(user_id=str(principal.user_id)))

    @app.get(
        "/api/v1/protected-resource",
        response_model=ApiResponse[ProtectedResourceResponse],
        operation_id="getProtectedResource",
        responses=problem_responses(401, 404, 500),
    )
    async def get_protected_resource(
        principal: Principal = Depends(get_principal),
    ) -> ApiResponse[ProtectedResourceResponse]:
        value = get_owned_resource(
            principal=principal, repository_lookup=resource_lookup
        )
        return ApiResponse(data=ProtectedResourceResponse(value=value))

    register_exception_handlers(app)
    app.include_router(captures_router, prefix="/api/v1")
    return app


configure_logging()
app = create_app()
