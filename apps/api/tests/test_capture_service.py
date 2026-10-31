import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid7

import pytest
from sqlalchemy.exc import IntegrityError

from hibi.modules.captures.errors import (
    CaptureNotFoundError,
    CaptureTextInvalidError,
    IdempotencyKeyConflictError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    MalformedCursorError,
)
from hibi.modules.captures.service import CaptureService
from hibi.modules.captures.types import (
    Capture,
    CreateCaptureCommand,
    ListCapturesQuery,
    UpdateCaptureCommand,
)

_KEY = "11111111-1111-4111-8111-111111111111"


def _hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _integrity_error() -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception("unique_violation"))


class FakeSession:
    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeCaptureRepository:
    def __init__(self) -> None:
        self.captures: list[Capture] = []
        self._create_attempts = 0
        self._raise_on_create: IntegrityError | None = None
        self._row_after_conflict: Capture | None = None

    def fail_create_then_return(self, existing: Capture) -> None:
        self._raise_on_create = _integrity_error()
        self._row_after_conflict = existing

    async def get_by_id(self, user_id: UUID, *, capture_id: UUID) -> Capture | None:
        for capture in self.captures:
            if capture.id == capture_id and capture.user_id == user_id:
                return capture
        return None

    async def get_by_idempotency_key(self, user_id: UUID, *, key: str) -> Capture | None:
        for capture in self.captures:
            if capture.user_id == user_id and capture.idempotency_key == key:
                return capture
        if (
            self._create_attempts > 0
            and self._row_after_conflict is not None
            and self._row_after_conflict.user_id == user_id
            and self._row_after_conflict.idempotency_key == key
        ):
            return self._row_after_conflict
        return None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int,
        start_created_at: datetime | None = None,
        start_capture_id: UUID | None = None,
    ) -> list[Capture]:
        rows = [capture for capture in self.captures if capture.user_id == user_id]
        rows.sort(key=lambda capture: (capture.created_at, capture.id), reverse=True)
        if start_created_at is not None and start_capture_id is not None:
            rows = [
                capture
                for capture in rows
                if (capture.created_at, capture.id) < (start_created_at, start_capture_id)
            ]
        return rows[:limit]

    async def create_capture(
        self,
        user_id: UUID,
        *,
        capture_id: UUID,
        raw_text: str,
        idempotency_key: str,
        request_hash: str,
        outbox_id: UUID,
    ) -> Capture:
        self._create_attempts += 1
        if self._raise_on_create is not None:
            error = self._raise_on_create
            self._raise_on_create = None
            raise error
        now = datetime.now(UTC)
        capture = Capture(
            id=capture_id,
            user_id=user_id,
            raw_text=raw_text,
            status="pending",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            processing_generation=1,
            created_at=now,
            updated_at=now,
        )
        self.captures.append(capture)
        return capture

    async def update_capture(
        self, user_id: UUID, *, capture_id: UUID, raw_text: str
    ) -> Capture | None:
        for index, capture in enumerate(self.captures):
            if capture.id != capture_id or capture.user_id != user_id:
                continue
            updated = Capture(
                id=capture.id,
                user_id=capture.user_id,
                raw_text=raw_text,
                status=capture.status,
                idempotency_key=capture.idempotency_key,
                request_hash=capture.request_hash,
                processing_generation=capture.processing_generation,
                created_at=capture.created_at,
                updated_at=datetime.now(UTC),
            )
            self.captures[index] = updated
            return updated
        return None

    async def delete_capture(self, user_id: UUID, *, capture_id: UUID) -> bool:
        for index, capture in enumerate(self.captures):
            if capture.id == capture_id and capture.user_id == user_id:
                del self.captures[index]
                return True
        return False


def _service(
    repo: FakeCaptureRepository | None = None,
) -> tuple[CaptureService, FakeCaptureRepository, FakeSession]:
    repository = repo or FakeCaptureRepository()
    session = FakeSession()
    return CaptureService(session, repository), repository, session  # type: ignore[arg-type]


def _create_command(
    user_id: UUID,
    *,
    raw_text: str = "牛乳を買う",
    idempotency_key: str | None = _KEY,
) -> CreateCaptureCommand:
    return CreateCaptureCommand(
        user_id=user_id, raw_text=raw_text, idempotency_key=idempotency_key
    )


@pytest.mark.asyncio
async def test_create_capture_trims_and_marks_pending() -> None:
    service, repo, _session = _service()
    user_id = uuid4()

    result = await service.create_capture(
        _create_command(user_id, raw_text="  牛乳を買う  ")
    )

    assert result.created is True
    assert result.capture.status == "pending"
    assert result.capture.raw_text == "牛乳を買う"
    assert result.capture.request_hash == _hash("牛乳を買う")
    assert len(repo.captures) == 1


@pytest.mark.asyncio
async def test_create_capture_replays_same_key_and_body() -> None:
    service, repo, _session = _service()
    user_id = uuid4()

    first = await service.create_capture(_create_command(user_id))
    second = await service.create_capture(_create_command(user_id))

    assert second.created is False
    assert second.capture.id == first.capture.id
    assert len(repo.captures) == 1


@pytest.mark.asyncio
async def test_create_capture_conflicts_when_key_reused_with_different_body() -> None:
    service, _repo, _session = _service()
    user_id = uuid4()
    await service.create_capture(_create_command(user_id, raw_text="牛乳を買う"))

    with pytest.raises(IdempotencyKeyConflictError):
        await service.create_capture(_create_command(user_id, raw_text="卵を買う"))


@pytest.mark.asyncio
async def test_create_capture_rejects_missing_or_short_key() -> None:
    service, _repo, _session = _service()
    user_id = uuid4()

    with pytest.raises(IdempotencyKeyRequiredError):
        await service.create_capture(_create_command(user_id, idempotency_key=None))
    with pytest.raises(IdempotencyKeyRequiredError):
        await service.create_capture(_create_command(user_id, idempotency_key=""))
    with pytest.raises(IdempotencyKeyInvalidError):
        await service.create_capture(_create_command(user_id, idempotency_key="short"))


@pytest.mark.asyncio
async def test_create_and_update_reject_blank_or_too_long_text() -> None:
    service, _repo, _session = _service()
    user_id = uuid4()

    with pytest.raises(CaptureTextInvalidError):
        await service.create_capture(_create_command(user_id, raw_text="   "))
    with pytest.raises(CaptureTextInvalidError):
        await service.create_capture(_create_command(user_id, raw_text="a" * 2001))

    created = await service.create_capture(_create_command(user_id))
    with pytest.raises(CaptureTextInvalidError):
        await service.update_capture(
            UpdateCaptureCommand(
                user_id=user_id, capture_id=created.capture.id, raw_text="   "
            )
        )


@pytest.mark.asyncio
async def test_get_update_delete_raise_not_found_for_missing_or_other_user() -> None:
    service, _repo, _session = _service()
    owner_id = uuid4()
    other_id = uuid4()
    created = await service.create_capture(_create_command(owner_id))
    missing_id = uuid7()

    with pytest.raises(CaptureNotFoundError):
        await service.get_capture(owner_id, missing_id)
    with pytest.raises(CaptureNotFoundError):
        await service.get_capture(other_id, created.capture.id)
    with pytest.raises(CaptureNotFoundError):
        await service.update_capture(
            UpdateCaptureCommand(
                user_id=other_id, capture_id=created.capture.id, raw_text="卵を買う"
            )
        )
    with pytest.raises(CaptureNotFoundError):
        await service.delete_capture(other_id, created.capture.id)

    await service.delete_capture(owner_id, created.capture.id)
    with pytest.raises(CaptureNotFoundError):
        await service.get_capture(owner_id, created.capture.id)


@pytest.mark.asyncio
async def test_list_captures_excludes_others_and_orders_newest_first() -> None:
    service, _repo, _session = _service()
    owner_id = uuid4()
    other_id = uuid4()

    older = await service.create_capture(
        _create_command(owner_id, raw_text="先に書いた", idempotency_key=f"{_KEY}a")
    )
    newer = await service.create_capture(
        _create_command(owner_id, raw_text="後に書いた", idempotency_key=f"{_KEY}b")
    )
    await service.create_capture(
        _create_command(other_id, raw_text="他人のメモ", idempotency_key=f"{_KEY}c")
    )

    page = await service.list_captures(
        ListCapturesQuery(user_id=owner_id, limit=10, cursor=None)
    )

    assert [item.id for item in page.items] == [newer.capture.id, older.capture.id]
    assert all(item.user_id == owner_id for item in page.items)
    assert page.has_next_page is False
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_list_captures_rejects_malformed_cursor() -> None:
    service, _repo, _session = _service()

    with pytest.raises(MalformedCursorError):
        await service.list_captures(
            ListCapturesQuery(user_id=uuid4(), limit=20, cursor="not-a-cursor")
        )


@pytest.mark.asyncio
async def test_create_capture_replays_after_integrity_error_when_hash_matches() -> None:
    repo = FakeCaptureRepository()
    service, repo, session = _service(repo)
    user_id = uuid4()
    winner = Capture(
        id=uuid7(),
        user_id=user_id,
        raw_text="牛乳を買う",
        status="pending",
        idempotency_key=_KEY,
        request_hash=_hash("牛乳を買う"),
        processing_generation=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.fail_create_then_return(winner)

    result = await service.create_capture(_create_command(user_id))

    assert result.created is False
    assert result.capture.id == winner.id
    assert session.rolled_back is True
    assert len(repo.captures) == 0


@pytest.mark.asyncio
async def test_create_capture_conflicts_after_integrity_error_when_hash_differs() -> None:
    repo = FakeCaptureRepository()
    service, repo, session = _service(repo)
    user_id = uuid4()
    winner = Capture(
        id=uuid7(),
        user_id=user_id,
        raw_text="卵を買う",
        status="pending",
        idempotency_key=_KEY,
        request_hash=_hash("卵を買う"),
        processing_generation=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.fail_create_then_return(winner)

    with pytest.raises(IdempotencyKeyConflictError):
        await service.create_capture(_create_command(user_id, raw_text="牛乳を買う"))
    assert session.rolled_back is True
