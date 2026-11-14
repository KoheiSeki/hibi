from typing import cast
from uuid import UUID

from hibi.modules.profiles.repository import ProfileRepository


class FakeProfileRepository:
    """`ProfileRepository` の代わりに、決まった timezone を返す fake。"""

    def __init__(self, timezone: str = "Asia/Tokyo") -> None:
        self.timezone = timezone
        self.lookups: list[UUID] = []

    async def get_timezone(self, user_id: UUID) -> str:
        self.lookups.append(user_id)
        return self.timezone


def as_profile_repository(fake: FakeProfileRepository) -> ProfileRepository:
    """fake を `CaptureService` に渡せる型にする。"""
    return cast(ProfileRepository, fake)
