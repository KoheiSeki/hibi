from datetime import UTC, date, datetime, time, timedelta

from hibi.core.timezone import zone_for

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

    local = _local_now(now, timezone=timezone)
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

    local = _local_now(now, timezone=timezone)
    if local.weekday() != 0 or local.hour < DIGEST_HOUR:
        return None
    return local.date() - timedelta(days=7)


def local_day_start(day: date, *, timezone: str) -> datetime:
    """ユーザーの暦日の、現地 0 時を UTC で返す。

    週次レビューの集計で、期間の境界(月曜の 0 時)を求めるのに使う。24 時間を足さず、
    暦日と現地の 0 時から求めるので、夏時間の日でも、境界が正しい。不正な timezone 名は
    UTC として扱う。

    Args:
        day: ユーザーの暦日。
        timezone: ユーザーの IANA 名。

    Returns:
        その暦日の現地 0 時に当たる、UTC の aware な datetime。
    """

    zone = zone_for(timezone)
    return datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)


def _local_now(now: datetime, *, timezone: str) -> datetime:
    """`now` を、ユーザーの timezone の現地時刻に直す。

    現地の暦日と時刻を求める判定が、同じ変換を共有するための関数。不正な
    timezone 名は UTC として扱う。

    Args:
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。

    Returns:
        同じ瞬間を、ユーザーの timezone で表した datetime。
    """

    return now.astimezone(zone_for(timezone))
