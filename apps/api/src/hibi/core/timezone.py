from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def utc_now() -> datetime:
    """現在時刻を、UTC の aware な datetime で返す。

    service の `clock` の既定値に使う。テストでは、固定の時刻を返す関数に差し替える。
    保存と比較に使う時刻は、すべて UTC の aware な datetime に揃える。
    """

    return datetime.now(UTC)


def zone_for(timezone: str) -> ZoneInfo:
    """IANA 名から ZoneInfo を返す。

    Args:
        timezone: IANA の timezone 名。例は `Asia/Tokyo`。

    Returns:
        名前に対応する ZoneInfo。存在しない名前や不正な名前は UTC。
    """

    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo("UTC")


def to_local(now: datetime, *, timezone: str) -> datetime:
    """`now` を、ユーザーの timezone の現地時刻に直す。

    現地の暦日や時刻を求める判定が、同じ変換を共有するための関数。不正な
    timezone 名は UTC として扱う。

    Args:
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。

    Returns:
        同じ瞬間を、ユーザーの timezone で表した datetime。
    """

    return now.astimezone(zone_for(timezone))


def local_day_start(day: date, *, timezone: str) -> datetime:
    """ユーザーの暦日の、現地 0 時を UTC で返す。

    今日の終わり(翌日の 0 時)や、週次レビューの期間の境界を求めるのに使う。
    24 時間を足さず、暦日と現地の 0 時から求めるので、夏時間の日でも、境界が正しい。
    不正な timezone 名は UTC として扱う。

    Args:
        day: ユーザーの暦日。
        timezone: ユーザーの IANA 名。

    Returns:
        その暦日の現地 0 時に当たる、UTC の aware な datetime。
    """

    return datetime.combine(day, time.min, tzinfo=zone_for(timezone)).astimezone(UTC)
