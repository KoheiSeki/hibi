from datetime import date, datetime, timedelta

from hibi.core.timezone import to_local

DIGEST_HOUR = 7


def daily_period_start(now: datetime, *, timezone: str) -> date | None:
    """日次ダイジェストを今作るべきなら、その日の暦日を返す。

    ユーザーの現地時刻が `DIGEST_HOUR` 時以降のときだけ返す。前なら None で、まだ作らない。
    暦日と時刻は、`now` をユーザーの timezone に直して決める。夏時間の日でも、
    現地の 7 時を過ぎてから作る。不正な timezone 名は UTC として扱う。

    Args:
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。

    Returns:
        現地の暦日。作る時刻の前なら None。
    """

    local = to_local(now, timezone=timezone)
    return local.date() if local.hour >= DIGEST_HOUR else None


def weekly_period_start(now: datetime, *, timezone: str) -> date | None:
    """週次レビューを今作るべきなら、対象の週の月曜を返す。

    ユーザーの現地が月曜で、`DIGEST_HOUR` 時以降のときだけ返す。対象は先週(月曜から
    日曜)で、先週の月曜の暦日を返す。月曜以外と、月曜の作る時刻の前は None で、
    まだ作らない。月曜を過ぎたら、前の週の分は作らない。曜日は、UTC ではなく
    `now` をユーザーの timezone に直して決める。

    Args:
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。不正な名前は UTC として扱う。

    Returns:
        先週の月曜の暦日。作る時刻でなければ None。
    """

    local = to_local(now, timezone=timezone)
    if local.weekday() != 0 or local.hour < DIGEST_HOUR:
        return None
    return local.date() - timedelta(days=7)
