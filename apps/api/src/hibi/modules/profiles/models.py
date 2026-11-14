from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column

from hibi.db.base import Base


class ProfileModel(Base):
    """`app.profiles` の読み取り用モデル。

    プロフィールの作成は Auth のトリガーが行い、API は書き込まない。
    必要な列(user_id と timezone)だけを持つ。
    """

    __tablename__ = "profiles"
    __table_args__ = {"schema": "app"}  # noqa: RUF012

    user_id: Mapped[UUID] = mapped_column(primary_key=True)
    timezone: Mapped[str] = mapped_column()
