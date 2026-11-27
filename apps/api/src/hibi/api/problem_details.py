from hibi.core.models import ApiModel


class FieldProblem(ApiModel):
    pointer: str
    code: str
    detail: str


class ProblemDetails(ApiModel):
    type: str
    title: str
    status: int
    detail: str
    instance: str | None = None
    request_id: str
    errors: list[FieldProblem] | None = None
