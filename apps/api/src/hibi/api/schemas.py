from pydantic import Field

from hibi.core.models import ApiModel


class ApiResponse[DataT](ApiModel):
    data: DataT


class HealthResponse(ApiModel):
    status: str


class EchoRequest(ApiModel):
    message: str = Field(min_length=1, max_length=2000)


class EchoResponse(ApiModel):
    message: str


class UserResponse(ApiModel):
    user_id: str


class ProtectedResourceResponse(ApiModel):
    value: str
