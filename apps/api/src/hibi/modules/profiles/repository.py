from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.modules.profiles.models import ProfileModel


class ProfileRepository:
    """プロフィールの永続化。今は timezone の読み取りだけ。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_timezone(self, user_id: UUID) -> str:
        """ユーザーの timezone を返す。

        Args:
            user_id: 所有者。

        Returns:
            プロフィールの IANA 名。プロフィールが無ければ UTC。
            名前の検証はせず、不正な名前は `zone_for` が UTC に倒す。
        """

        timezone = await self._session.scalar(
            select(ProfileModel.timezone).where(ProfileModel.user_id == user_id)
        )
        return timezone if timezone is not None else "UTC"
