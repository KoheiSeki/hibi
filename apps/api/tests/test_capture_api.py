from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from hibi.api.dependencies import get_principal
from hibi.api.main import create_app
from hibi.auth.principal import Principal
from hibi.modules.captures.errors import (
    CaptureNotEditableError,
    CaptureNotFoundError,
    CaptureNotRetryableError,
    CaptureTextInvalidError,
    IdempotencyKeyConflictError,
    IdempotencyKeyRequiredError,
    MalformedCursorError,
)
from hibi.modules.captures.router import _get_capture_service
from hibi.modules.captures.types import (
    Capture,
    CapturePage,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    UpdateCaptureCommand,
)

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
CAPTURE_ID = UUID("0198f0c2-7c1a-7000-8000-000000000001")
MISSING_ID = UUID("0198f0c2-7c1a-7000-8000-000000000099")
_NOW = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
_KEY = "idem-key-01"


def _capture(**overrides: object) -> Capture:
    values: dict[str, object] = {
        "id": CAPTURE_ID,
        "user_id": OWNER_ID,
        "raw_text": "牛乳を買う",
        "status": "pending",
        "idempotency_key": _KEY,
        "request_hash": "hash",
        "processing_generation": 1,
        "category": None,
        "route": None,
        "urgency": None,
        "confidence": None,
        "policy_version": None,
        "question_version": None,
        "processed_at": None,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    values.update(overrides)
    return Capture(**values)  # type: ignore[arg-type]


class FakeCaptureService:
    def __init__(self) -> None:
        self.captures: dict[UUID, Capture] = {}
        self.created = True
        self.create_error: Exception | None = None

    async def create_capture(self, command: CreateCaptureCommand) -> CreateCaptureResult:
        if self.create_error is not None:
            raise self.create_error
        if command.idempotency_key is None or command.idempotency_key == "":
            raise IdempotencyKeyRequiredError()
        stripped = command.raw_text.strip()
        if stripped == "":
            raise CaptureTextInvalidError()
        capture = _capture(user_id=command.user_id, raw_text=stripped)
        if self.created:
            self.captures[capture.id] = capture
        return CreateCaptureResult(capture=capture, created=self.created)

    async def get_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        capture = self.captures.get(capture_id)
        if capture is None or capture.user_id != user_id:
            raise CaptureNotFoundError(capture_id)
        return capture

    async def list_captures(self, query: ListCapturesQuery) -> CapturePage:
        if query.cursor:
            raise MalformedCursorError()
        items = [capture for capture in self.captures.values() if capture.user_id == query.user_id]
        return CapturePage(items=items, next_cursor=None, has_next_page=False)

    async def update_capture(self, command: UpdateCaptureCommand) -> Capture:
        capture = self.captures.get(command.capture_id)
        if capture is None or capture.user_id != command.user_id:
            raise CaptureNotFoundError(command.capture_id)
        if capture.status in {"processing", "completed"}:
            raise CaptureNotEditableError()
        stripped = command.raw_text.strip()
        if stripped == "":
            raise CaptureTextInvalidError()
        updated = _capture(
            id=capture.id,
            user_id=capture.user_id,
            raw_text=stripped,
            status=capture.status,
            processing_generation=capture.processing_generation,
        )
        self.captures[updated.id] = updated
        return updated

    async def delete_capture(self, user_id: UUID, capture_id: UUID) -> None:
        capture = self.captures.get(capture_id)
        if capture is None or capture.user_id != user_id:
            raise CaptureNotFoundError(capture_id)
        del self.captures[capture_id]

    async def retry_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        capture = self.captures.get(capture_id)
        if capture is None or capture.user_id != user_id:
            raise CaptureNotFoundError(capture_id)
        if capture.status != "failed":
            raise CaptureNotRetryableError()
        retried = _capture(
            id=capture.id,
            user_id=capture.user_id,
            raw_text=capture.raw_text,
            status="pending",
            processing_generation=capture.processing_generation + 1,
        )
        self.captures[capture_id] = retried
        return retried


def _client(fake: FakeCaptureService, *, authenticated: bool = True) -> TestClient:
    app = create_app()
    app.dependency_overrides[_get_capture_service] = lambda: fake
    if authenticated:
        app.dependency_overrides[get_principal] = lambda: Principal(
            user_id=OWNER_ID, permissions=frozenset()
        )
    return TestClient(app)


def test_capture_endpoints_reject_missing_token() -> None:
    client = _client(FakeCaptureService(), authenticated=False)
    path = f"/api/v1/captures/{CAPTURE_ID}"
    requests = [
        client.post(
            "/api/v1/captures",
            json={"rawText": "牛乳を買う"},
            headers={"Idempotency-Key": _KEY},
        ),
        client.get("/api/v1/captures"),
        client.get(path),
        client.patch(path, json={"rawText": "低脂肪乳を買う"}),
        client.delete(path),
        client.post(f"{path}/retry"),
    ]
    for response in requests:
        assert response.status_code == 401
        assert response.json()["type"].endswith("/unauthorized")


def test_create_capture_returns_202_and_location() -> None:
    fake = FakeCaptureService()
    response = _client(fake).post(
        "/api/v1/captures",
        json={"rawText": "牛乳を買う"},
        headers={"Idempotency-Key": _KEY},
    )
    assert response.status_code == 202
    body = response.json()["data"]
    assert body["status"] == "pending"
    assert body["rawText"] == "牛乳を買う"
    assert response.headers["location"] == f"/api/v1/captures/{body['id']}"


def test_create_capture_replay_returns_200_with_same_id() -> None:
    fake = FakeCaptureService()
    fake.created = False
    fake.captures[CAPTURE_ID] = _capture()
    response = _client(fake).post(
        "/api/v1/captures",
        json={"rawText": "牛乳を買う"},
        headers={"Idempotency-Key": _KEY},
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(CAPTURE_ID)


def test_create_capture_rejects_idempotency_key_conflict() -> None:
    fake = FakeCaptureService()
    fake.create_error = IdempotencyKeyConflictError()
    response = _client(fake).post(
        "/api/v1/captures",
        json={"rawText": "別の本文"},
        headers={"Idempotency-Key": _KEY},
    )
    assert response.status_code == 409
    assert response.json()["type"].endswith("/idempotency-key-conflict")


def test_create_capture_rejects_missing_idempotency_key() -> None:
    response = _client(FakeCaptureService()).post(
        "/api/v1/captures", json={"rawText": "牛乳を買う"}
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("/idempotency-key-required")


@pytest.mark.parametrize("raw_text", ["", "   "])
def test_create_capture_rejects_empty_raw_text(raw_text: str) -> None:
    response = _client(FakeCaptureService()).post(
        "/api/v1/captures",
        json={"rawText": raw_text},
        headers={"Idempotency-Key": _KEY},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("/validation-error")
    assert body["errors"][0]["pointer"] == "/rawText"


def test_get_own_capture_returns_200() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture()
    response = _client(fake).get(f"/api/v1/captures/{CAPTURE_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(CAPTURE_ID)


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_foreign_capture_is_hidden_as_not_found(method: str) -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(user_id=OTHER_ID)
    client = _client(fake)
    path = f"/api/v1/captures/{CAPTURE_ID}"
    if method == "get":
        response = client.get(path)
    elif method == "patch":
        response = client.patch(path, json={"rawText": "低脂肪乳を買う"})
    else:
        response = client.delete(path)
    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")


def test_missing_capture_returns_404() -> None:
    response = _client(FakeCaptureService()).get(f"/api/v1/captures/{MISSING_ID}")
    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")


def test_list_captures_excludes_other_users_rows() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture()
    other_id = UUID("0198f0c2-7c1a-7000-8000-000000000002")
    fake.captures[other_id] = _capture(id=other_id, user_id=OTHER_ID, raw_text="秘密")
    response = _client(fake).get("/api/v1/captures")
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]]
    assert ids == [str(CAPTURE_ID)]
    assert response.json()["meta"] == {"nextCursor": None, "hasNextPage": False}


def test_delete_capture_then_get_returns_404() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture()
    client = _client(fake)
    delete_response = client.delete(f"/api/v1/captures/{CAPTURE_ID}")
    assert delete_response.status_code == 204
    get_response = client.get(f"/api/v1/captures/{CAPTURE_ID}")
    assert get_response.status_code == 404
    assert get_response.json()["type"].endswith("/capture-not-found")


@pytest.mark.parametrize("capture_status", ["processing", "completed"])
def test_update_capture_rejects_non_editable_status(capture_status: str) -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status=capture_status)

    response = _client(fake).patch(
        f"/api/v1/captures/{CAPTURE_ID}",
        json={"rawText": "更新後"},
    )

    assert response.status_code == 409
    assert response.json()["type"].endswith("/capture-not-editable")


def test_retry_failed_capture_returns_202_and_location() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="failed")

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/retry")

    assert response.status_code == 202
    assert response.json()["data"]["status"] == "pending"
    assert response.headers["location"] == f"/api/v1/captures/{CAPTURE_ID}"


@pytest.mark.parametrize("capture_status", ["pending", "processing", "completed"])
def test_retry_capture_rejects_non_failed_status(capture_status: str) -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status=capture_status)

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/retry")

    assert response.status_code == 409
    assert response.json()["type"].endswith("/capture-not-retryable")


def test_retry_foreign_capture_is_hidden_as_not_found() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(user_id=OTHER_ID, status="failed")

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/retry")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")


def test_list_captures_rejects_malformed_cursor() -> None:
    response = _client(FakeCaptureService()).get(
        "/api/v1/captures", params={"cursor": "not-a-cursor"}
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("/malformed-cursor")
