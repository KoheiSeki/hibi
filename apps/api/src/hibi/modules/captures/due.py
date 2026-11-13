import re
from datetime import UTC, datetime, time, timedelta

from hibi.core.timezone import zone_for

_DAY = r"今日|明日|明後日"
_REMIND_PATTERN = re.compile(
    rf"(?:(?P<day>{_DAY})\s*の?\s*)?"
    r"(?P<meridiem>午前|午後)?\s*(?P<hour>\d{1,2})\s*時(?!間)"
    r"(?:\s*(?P<minute>\d{1,2})\s*分|(?P<half>半))?"
    rf"|(?P<day_only>{_DAY})"
)

_DAY_OFFSETS = {"今日": 0, "明日": 1, "明後日": 2}


def extract_remind_text(raw_text: str) -> str | None:
    """本文から、日と時刻の表現を 1 つの文字列として取り出す。

    日は `今日`、`明日`、`明後日`。時刻は `午前` か `午後` を任意で付けた `N時` と、
    任意の `M分` か `半`。時刻が無く日だけでも取り出す。`3時間` のような
    所要時間は時刻として扱わない。

    Args:
        raw_text: Capture の本文。

    Returns:
        一致した部分を前後の空白なしで返す。表現が無ければ None。
    """

    matched = _REMIND_PATTERN.search(raw_text)
    return matched.group(0).strip() if matched else None


def parse_due_at(remind_text: str, *, now: datetime, timezone: str) -> datetime | None:
    """remind_text を、ユーザーの timezone での期限に直す。

    日は now をユーザーの timezone に直した暦日から数えるので、夏時間の日でも
    同じ時刻になる。時刻が無ければその日の 23 時 59 分。`午後` で時が 12 未満
    なら 12 時間足す。

    Args:
        remind_text: `extract_remind_text` が返した時刻の表現。
        now: 現在時刻。aware な datetime。
        timezone: ユーザーの IANA 名。不正な名前は UTC として扱う。

    Returns:
        UTC の aware な datetime。表現が無い、または時と分が範囲外なら None。
    """

    matched = _REMIND_PATTERN.search(remind_text)
    if matched is None:
        return None

    day_word = matched.group("day") or matched.group("day_only")
    day_offset = _DAY_OFFSETS[day_word] if day_word else 0

    hour_text = matched.group("hour")
    if hour_text is None:
        hour, minute = 23, 59
    else:
        hour = int(hour_text)
        meridiem = matched.group("meridiem")
        if hour < 12 and meridiem == "午後":
            hour += 12
        minute = 30 if matched.group("half") == "半" else int(matched.group("minute") or 0)

    if hour > 23 or minute > 59:
        return None

    zone = zone_for(timezone)
    target_date = now.astimezone(zone).date() + timedelta(days=day_offset)
    local_due = datetime.combine(target_date, time(hour, minute), tzinfo=zone)
    return local_due.astimezone(UTC)
