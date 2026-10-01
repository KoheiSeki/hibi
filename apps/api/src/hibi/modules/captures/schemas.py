from datetime import datetime
from uuid import UUID

from hibi.core.models import ApiModel


class CreateCaptureRequest(ApiModel):
    raw_text: str


class UpdateCaptureRequest(ApiModel):
    raw_text: str


class CaptureResponse(ApiModel):
    id: UUID
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
