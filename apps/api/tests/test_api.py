from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from hibi.api.dependencies import get_principal
from hibi.api.main import create_app
from hibi.auth.principal import Principal


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_uses_success_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"data": {"status": "ok"}}
    assert response.headers["x-request-id"]


def test_validation_error_is_problem_details(client: TestClient) -> None:
    response = client.post("/api/v1/echo", json={"message": ""})
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"].endswith("/validation-error")
    assert body["requestId"] == response.headers["x-request-id"]
    assert body["errors"][0]["pointer"] == "/message"


def test_protected_endpoint_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["type"].endswith("/unauthorized")


def test_protected_endpoint_uses_verified_principal(client: TestClient) -> None:
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    app = create_app()
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=user_id, permissions=frozenset()
    )
    response = TestClient(app).get("/api/v1/me")
    assert response.status_code == 200
    assert response.json() == {"data": {"userId": str(user_id)}}


def test_resource_lookup_passes_principal_user_to_repository() -> None:
    user_id = UUID("11111111-1111-4111-8111-111111111111")
    seen_user_ids: list[UUID] = []

    def repository_lookup(owner_id: UUID) -> str:
        seen_user_ids.append(owner_id)
        return "owned-resource"

    app = create_app(resource_lookup=repository_lookup)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=user_id, permissions=frozenset()
    )
    response = TestClient(app).get("/api/v1/protected-resource")
    assert response.json() == {"data": {"value": "owned-resource"}}
    assert seen_user_ids == [user_id]


def test_unexpected_error_preserves_request_id_in_header_and_problem() -> None:
    user_id = UUID("11111111-1111-4111-8111-111111111111")

    def failing_lookup(_owner_id: UUID) -> str:
        raise RuntimeError("database unavailable")

    app = create_app(resource_lookup=failing_lookup)
    app.dependency_overrides[get_principal] = lambda: Principal(
        user_id=user_id, permissions=frozenset()
    )
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/protected-resource",
        headers={"X-Request-ID": "request-500"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["x-request-id"] == "request-500"
    assert response.json()["requestId"] == "request-500"


def test_openapi_advertises_problem_details_media_type() -> None:
    schema = create_app().openapi()
    expected_responses = [
        ("/api/v1/health", "get", "500"),
        ("/api/v1/echo", "post", "422"),
        ("/api/v1/echo", "post", "500"),
        ("/api/v1/me", "get", "401"),
        ("/api/v1/me", "get", "500"),
        ("/api/v1/protected-resource", "get", "401"),
        ("/api/v1/protected-resource", "get", "404"),
        ("/api/v1/protected-resource", "get", "500"),
    ]

    for path, method, status in expected_responses:
        response = schema["paths"][path][method]["responses"][status]
        assert set(response["content"]) == {"application/problem+json"}
        assert response["content"]["application/problem+json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemDetails"
        }
