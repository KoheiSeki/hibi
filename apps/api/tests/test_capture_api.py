from datetime import UTC, datetime
from typing import TYPE_CHECKING
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
    ScenarioNotAcceptableError,
)
from hibi.modules.captures.router import _get_capture_service
from hibi.modules.captures.types import (
    Capture,
    CapturePage,
    CaptureScenario,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    UpdateCaptureCommand,
)

if TYPE_CHECKING:
    from hibi.modules.captures.types import TodayCapturesQuery

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
        "clarification_text": None,
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
        self.scenarios: dict[UUID, str] = {}
        self.search_calls: list[tuple[str, str]] = []
        self.today_limits: list[int] = []
        self.done_calls: list[tuple[UUID, bool]] = []

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

    async def search_captures(self, query: SearchCapturesQuery) -> list[Capture]:
        self.search_calls.append((query.q, query.mode))
        return [
            capture
            for capture in self.captures.values()
            if capture.user_id == query.user_id and query.q in capture.raw_text
        ]

    async def list_today_captures(self, query: TodayCapturesQuery) -> list[Capture]:
        self.today_limits.append(query.limit)
        return [capture for capture in self.captures.values() if capture.user_id == query.user_id]

    async def set_capture_scenario_done(
        self, user_id: UUID, capture_id: UUID, *, done: bool
    ) -> Capture:
        capture = self.captures.get(capture_id)
        if capture is None or capture.user_id != user_id or capture_id not in self.scenarios:
            raise CaptureNotFoundError(capture_id)
        self.done_calls.append((capture_id, done))
        return capture

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

    async def accept_capture_scenario(self, user_id: UUID, capture_id: UUID) -> Capture:
        capture = self.captures.get(capture_id)
        if capture is None or capture.user_id != user_id:
            raise CaptureNotFoundError(capture_id)
        scenario_status = self.scenarios.get(capture_id)
        if scenario_status is None:
            raise CaptureNotFoundError(capture_id)
        if scenario_status != "proposed":
            raise ScenarioNotAcceptableError()
        self.scenarios[capture_id] = "accepted"
        return capture


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
        client.post(f"{path}/scenario/accept"),
        client.get("/api/v1/captures/today"),
        client.post(f"{path}/scenario/done"),
        client.delete(f"{path}/scenario/done"),
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
    body = response.json()["data"]
    assert body["id"] == str(CAPTURE_ID)
    assert body["clarificationText"] is None
    assert body["scenario"] is None


def test_get_own_capture_returns_clarification_text() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(clarification_text="それはいつ買いますか？")  # noqa: RUF001
    response = _client(fake).get(f"/api/v1/captures/{CAPTURE_ID}")
    assert response.status_code == 200
    assert response.json()["data"]["clarificationText"] == "それはいつ買いますか？"  # noqa: RUF001


def test_get_own_capture_returns_scenario() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(
        status="completed",
        scenario=CaptureScenario(
            route="expense",
            status="proposed",
            title="ランチ",
            amount=1200,
            remind_text=None,
            policy_version="capture-scenario-v1",
        ),
    )

    response = _client(fake).get(f"/api/v1/captures/{CAPTURE_ID}")

    assert response.status_code == 200
    assert response.json()["data"]["scenario"] == {
        "route": "expense",
        "status": "proposed",
        "title": "ランチ",
        "amount": 1200,
        "remindText": None,
        "policyVersion": "capture-scenario-v1",
        "dueAt": None,
        "doneAt": None,
    }


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


def test_accept_proposed_scenario_returns_completed_capture() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")
    fake.scenarios[CAPTURE_ID] = "proposed"

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/scenario/accept")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert fake.scenarios[CAPTURE_ID] == "accepted"


def test_accept_missing_scenario_returns_404() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/scenario/accept")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")


def test_accept_foreign_scenario_is_hidden_as_not_found() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(user_id=OTHER_ID, status="completed")
    fake.scenarios[CAPTURE_ID] = "proposed"

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/scenario/accept")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")
    assert fake.scenarios[CAPTURE_ID] == "proposed"


def test_accept_already_accepted_scenario_returns_409() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")
    fake.scenarios[CAPTURE_ID] = "accepted"

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/scenario/accept")

    assert response.status_code == 409
    assert response.json()["type"].endswith("/scenario-not-acceptable")


def test_list_captures_rejects_malformed_cursor() -> None:
    response = _client(FakeCaptureService()).get(
        "/api/v1/captures", params={"cursor": "not-a-cursor"}
    )
    assert response.status_code == 400
    assert response.json()["type"].endswith("/malformed-cursor")


def test_search_captures_returns_matching_captures() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["data"]] == [str(CAPTURE_ID)]
    assert fake.search_calls == [("牛乳", "keyword")]


def test_search_captures_passes_the_requested_mode() -> None:
    fake = FakeCaptureService()

    response = _client(fake).get(
        "/api/v1/captures/search", params={"q": "ミルク", "mode": "semantic"}
    )

    assert response.status_code == 200
    assert fake.search_calls == [("ミルク", "semantic")]


def test_search_captures_returns_an_empty_array_without_hits() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).get("/api/v1/captures/search", params={"q": "記事"})

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_search_captures_does_not_return_other_owners() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed", user_id=OTHER_ID)

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "あ" * 201},
        {"q": "牛乳", "mode": "bogus"},
    ],
    ids=["missing_q", "blank_q", "too_long_q", "bad_mode"],
)
def test_search_captures_rejects_invalid_query(params: dict[str, str]) -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/search", params=params)

    assert response.status_code == 422
    assert fake.search_calls == []


def test_search_captures_requires_a_token() -> None:
    response = _client(FakeCaptureService(), authenticated=False).get(
        "/api/v1/captures/search", params={"q": "牛乳"}
    )

    assert response.status_code == 401


def test_search_path_is_registered_before_the_capture_id_path() -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/search", params={"q": "牛乳"})

    # /{capture_id}が先に当たると"search"のUUIDパースで422になる
    assert response.status_code == 200


def test_today_returns_the_data_array_with_the_default_limit() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = _client(fake).get("/api/v1/captures/today")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [str(CAPTURE_ID)]
    assert fake.today_limits == [5]


def test_today_passes_the_requested_limit() -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/today", params={"limit": "3"})

    assert response.status_code == 200
    assert fake.today_limits == [3]


def test_today_returns_an_empty_array_without_captures() -> None:
    response = _client(FakeCaptureService()).get("/api/v1/captures/today")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_today_does_not_return_other_owners() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed", user_id=OTHER_ID)

    response = _client(fake).get("/api/v1/captures/today")

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize("limit", ["0", "21", "abc"])
def test_today_rejects_an_invalid_limit(limit: str) -> None:
    fake = FakeCaptureService()

    response = _client(fake).get("/api/v1/captures/today", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["errors"][0]["pointer"] == "/limit"
    assert fake.today_limits == []


def test_today_path_is_registered_before_the_capture_id_path() -> None:
    response = _client(FakeCaptureService()).get("/api/v1/captures/today")

    # /{capture_id}が先に当たると"today"のUUIDパースで422になる
    assert response.status_code == 200


def test_mark_scenario_done_returns_the_capture() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")
    fake.scenarios[CAPTURE_ID] = "accepted"

    response = _client(fake).post(f"/api/v1/captures/{CAPTURE_ID}/scenario/done")

    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(CAPTURE_ID)
    assert fake.done_calls == [(CAPTURE_ID, True)]


def test_unmark_scenario_done_returns_the_capture() -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")
    fake.scenarios[CAPTURE_ID] = "accepted"

    response = _client(fake).delete(f"/api/v1/captures/{CAPTURE_ID}/scenario/done")

    assert response.status_code == 200
    assert fake.done_calls == [(CAPTURE_ID, False)]


@pytest.mark.parametrize("method", ["post", "delete"])
def test_scenario_done_without_a_scenario_returns_404(method: str) -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(status="completed")

    response = getattr(_client(fake), method)(f"/api/v1/captures/{CAPTURE_ID}/scenario/done")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")
    assert fake.done_calls == []


@pytest.mark.parametrize("method", ["post", "delete"])
def test_scenario_done_of_another_owner_is_hidden_as_not_found(method: str) -> None:
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(user_id=OTHER_ID, status="completed")
    fake.scenarios[CAPTURE_ID] = "accepted"

    response = getattr(_client(fake), method)(f"/api/v1/captures/{CAPTURE_ID}/scenario/done")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/capture-not-found")
    assert fake.done_calls == []


def test_scenario_response_includes_the_deadline_and_completion_time() -> None:
    due_at = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)
    done_at = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    fake = FakeCaptureService()
    fake.captures[CAPTURE_ID] = _capture(
        status="completed",
        scenario=CaptureScenario(
            route="reminder",
            status="accepted",
            title="起こして",
            amount=None,
            remind_text="明日の 9 時",
            policy_version="capture-scenario-v1",
            due_at=due_at,
            done_at=done_at,
        ),
    )

    response = _client(fake).get(f"/api/v1/captures/{CAPTURE_ID}")

    scenario = response.json()["data"]["scenario"]
    assert datetime.fromisoformat(scenario["dueAt"]) == due_at
    assert datetime.fromisoformat(scenario["doneAt"]) == done_at
