from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
