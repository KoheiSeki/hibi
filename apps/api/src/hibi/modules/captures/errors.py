from uuid import UUID
from hibi.core.errors import ApplicationError


class IdempotencyKeyRequiredError(ApplicationError):
    problem_type = "idempotency-key-required"
    title = "Idempotency-Key required"
    status = 400
    detail = "Idempotency-Key header is required."


class IdempotencyKeyInvalidError(ApplicationError):
    problem_type = "idempotency-key-invalid"
    title = "Idempotency-Key invalid"
    status = 400
    detail = "Idempotency-Key is invalid."


class MalformedCursorError(ApplicationError):
    problem_type = "malformed-cursor"
    title = "Malformed cursor"
    status = 400
    detail = "The pagination cursor is invalid."


class IdempotencyKeyConflictError(ApplicationError):
    problem_type = "idempotency-key-conflict"
    title = "Idempotency-Key conflict"
    status = 409
    detail = "Idempotency-Key was reused with a different payload."


class CaptureNotFoundError(ApplicationError):
    problem_type = "capture-not-found"
    title = "Capture not found"
    status = 404
    detail = "The requested capture does not exist."

    def __init__(self, capture_id: UUID) -> None:
        self.capture_id = capture_id
        super().__init__()


class CaptureTextInvalidError(ApplicationError):
    problem_type = "validation-error"
    title = "Request validation failed"
    status = 422
    detail = "One or more fields are invalid."
