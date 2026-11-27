from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from hibi.api.dependencies import get_principal
from hibi.api.main import create_app
from hibi.auth.principal import Principal
from hibi.modules.digests.errors import (
    DigestReportNotFoundError,
    DigestReportNotRetryableError,
)
from hibi.modules.digests.router import _get_digest_service
from hibi.modules.digests.types import (
    DigestReport,
    ListDigestReportsQuery,
)

OWNER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("22222222-2222-4222-8222-222222222222")
REPORT_ID = UUID("0198f0c2-7c1a-7000-8000-000000000001")
OLDER_ID = UUID("0198f0c2-7c1a-7000-8000-000000000002")
_NOW = datetime(2026, 11, 10, 22, 0, tzinfo=UTC)
_CONTENT = {
    "items": [{"captureId": "c1", "title": "牛乳を買う", "dueAt": "2026-11-10T09:00:00Z"}],
    "overdueCount": 1,
    "dueTodayCount": 0,
    "doneYesterdayCount": 2,
}


def _report(**overrides: object) -> DigestReport:
    values: dict[str, object] = {
        "id": REPORT_ID,
        "user_id": OWNER_ID,
        "kind": "daily",
        "period_start": date(2026, 11, 11),
        "timezone": "Asia/Tokyo",
        "status": "ready",
        "content": _CONTENT,
        "content_version": "daily-digest-v1",
        "summary_model": None,
        "error_code": None,
        "generated_at": _NOW,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    values.update(overrides)
    return DigestReport(**values)  # type: ignore[arg-type]


class FakeDigestService:
    def __init__(self) -> None:
        self.reports: list[DigestReport] = []
        self.list_queries: list[ListDigestReportsQuery] = []
        self.retried: list[tuple[UUID, UUID]] = []

    async def list_reports(self, query: ListDigestReportsQuery) -> list[DigestReport]:
        self.list_queries.append(query)
        return [report for report in self.reports if report.user_id == query.user_id]

    async def retry_report(self, user_id: UUID, *, report_id: UUID) -> DigestReport:
        self.retried.append((user_id, report_id))
        report = next((report for report in self.reports if report.id == report_id), None)
        if report is None or report.user_id != user_id:
            raise DigestReportNotFoundError(report_id)
        if report.status != "failed":
            raise DigestReportNotRetryableError()
        return _report(
            id=report.id, status="pending", content=None, error_code=None, generated_at=None
        )


def _client(fake: FakeDigestService, *, authenticated: bool = True) -> TestClient:
    app = create_app()
    app.dependency_overrides[_get_digest_service] = lambda: fake
    if authenticated:
        app.dependency_overrides[get_principal] = lambda: Principal(
            user_id=OWNER_ID, permissions=frozenset()
        )
    return TestClient(app)


def test_digest_endpoints_require_a_token() -> None:
    client = _client(FakeDigestService(), authenticated=False)

    responses = [
        client.get("/api/v1/digest-reports"),
        client.post(f"/api/v1/digest-reports/{REPORT_ID}/retry"),
    ]

    for response in responses:
        assert response.status_code == 401
        assert response.json()["type"].endswith("/unauthorized")


def test_list_returns_the_data_array_in_the_service_order_with_the_default_limit() -> None:
    fake = FakeDigestService()
    fake.reports = [
        _report(id=REPORT_ID, period_start=date(2026, 11, 11)),
        _report(id=OLDER_ID, period_start=date(2026, 11, 10)),
    ]

    response = _client(fake).get("/api/v1/digest-reports")

    assert response.status_code == 200
    # 並び(新しい順)は service が決める。router は並べ替えない
    assert [item["id"] for item in response.json()["data"]] == [str(REPORT_ID), str(OLDER_ID)]
    [query] = fake.list_queries
    assert query == ListDigestReportsQuery(user_id=OWNER_ID, kind=None, from_date=None, limit=7)


def test_list_passes_kind_from_date_and_limit() -> None:
    fake = FakeDigestService()

    response = _client(fake).get(
        "/api/v1/digest-reports",
        params={"kind": "weekly", "fromDate": "2026-11-01", "limit": "30"},
    )

    assert response.status_code == 200
    [query] = fake.list_queries
    assert query == ListDigestReportsQuery(
        user_id=OWNER_ID, kind="weekly", from_date=date(2026, 11, 1), limit=30
    )


def test_list_returns_an_empty_array_without_reports() -> None:
    response = _client(FakeDigestService()).get("/api/v1/digest-reports")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_list_does_not_return_other_owners() -> None:
    fake = FakeDigestService()
    fake.reports = [_report(user_id=OTHER_ID)]

    response = _client(fake).get("/api/v1/digest-reports")

    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.parametrize(
    ("params", "pointer"),
    [
        ({"limit": "0"}, "/limit"),
        ({"limit": "31"}, "/limit"),
        ({"limit": "abc"}, "/limit"),
        ({"kind": "monthly"}, "/kind"),
        ({"fromDate": "not-a-date"}, "/fromDate"),
    ],
)
def test_list_rejects_invalid_parameters(params: dict[str, str], pointer: str) -> None:
    fake = FakeDigestService()

    response = _client(fake).get("/api/v1/digest-reports", params=params)

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")
    assert response.json()["errors"][0]["pointer"] == pointer
    assert fake.list_queries == []


def test_list_serializes_a_ready_report_in_camel_case_and_passes_the_content_through() -> None:
    fake = FakeDigestService()
    fake.reports = [_report()]

    response = _client(fake).get("/api/v1/digest-reports")

    [item] = response.json()["data"]
    assert item == {
        "id": str(REPORT_ID),
        "kind": "daily",
        "periodStart": "2026-11-11",
        "timezone": "Asia/Tokyo",
        "status": "ready",
        "content": _CONTENT,
        "contentVersion": "daily-digest-v1",
        "errorCode": None,
        "generatedAt": "2026-11-10T22:00:00Z",
    }


def test_list_returns_null_content_and_the_error_code_for_a_failed_report() -> None:
    fake = FakeDigestService()
    fake.reports = [
        _report(status="failed", content=None, error_code="generation_failed", generated_at=None)
    ]

    [item] = _client(fake).get("/api/v1/digest-reports").json()["data"]

    assert item["status"] == "failed"
    assert item["content"] is None
    assert item["errorCode"] == "generation_failed"
    assert item["generatedAt"] is None


def test_retry_returns_202_and_the_pending_report() -> None:
    fake = FakeDigestService()
    fake.reports = [_report(status="failed", content=None, error_code="generation_failed")]

    response = _client(fake).post(f"/api/v1/digest-reports/{REPORT_ID}/retry")

    assert response.status_code == 202
    data = response.json()["data"]
    assert data["id"] == str(REPORT_ID)
    assert data["status"] == "pending"
    assert data["errorCode"] is None
    assert fake.retried == [(OWNER_ID, REPORT_ID)]


@pytest.mark.parametrize("report_status", ["pending", "ready"])
def test_retry_returns_409_for_a_report_that_is_not_failed(report_status: str) -> None:
    fake = FakeDigestService()
    fake.reports = [_report(status=report_status)]

    response = _client(fake).post(f"/api/v1/digest-reports/{REPORT_ID}/retry")

    assert response.status_code == 409
    assert response.json()["type"].endswith("/digest-report-not-retryable")


@pytest.mark.parametrize("owner_id", [OTHER_ID, None], ids=["foreign", "missing"])
def test_retry_hides_a_foreign_or_missing_report_as_not_found(owner_id: UUID | None) -> None:
    fake = FakeDigestService()
    if owner_id is not None:
        fake.reports = [_report(user_id=owner_id, status="failed")]

    response = _client(fake).post(f"/api/v1/digest-reports/{REPORT_ID}/retry")

    assert response.status_code == 404
    assert response.json()["type"].endswith("/digest-report-not-found")


def test_retry_rejects_a_malformed_report_id() -> None:
    response = _client(FakeDigestService()).post("/api/v1/digest-reports/not-a-uuid/retry")

    assert response.status_code == 422
    assert response.json()["errors"][0]["pointer"] == "/report_id"
