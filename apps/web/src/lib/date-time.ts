const JST_TIME_ZONE = "Asia/Tokyo";

export function formatJstTime(timestamp: string): string {
  const date = new Date(timestamp);

  assertValidDate(date);

  return jstTimeFormatter.format(date);
}

export function formatJstDateTime(timestamp: string): string {
  const date = new Date(timestamp);

  assertValidDate(date);

  return jstDateTimeFormatter.format(date);
}

/**
 * 期限を、今日の期限なら時刻だけ、それ以外なら日付つきで整形する。
 *
 * Today には期限超過の行も並ぶ。昨日の 9 時と今日の 9 時を、時刻だけでは
 * 見分けられないため、今日でない期限には日付を足す。日付の境界は JST の暦日で決める。
 *
 * @param timestamp - ISO 8601 の期限。
 * @param now - 「今日」の基準にする時刻。テストで固定できるよう、引数にしている。
 * @returns `09:00`、`昨日 09:00`、`明日 09:00`、`11/08 09:00` のいずれか。
 */
export function formatJstDueLabel(
  timestamp: string,
  now: Date = new Date(),
): string {
  const date = new Date(timestamp);

  assertValidDate(date);

  const time = jstTimeFormatter.format(date);
  const dayOffset = jstDayNumber(date) - jstDayNumber(now);
  if (dayOffset === 0) {
    return time;
  }
  if (dayOffset === -1) {
    return `昨日 ${time}`;
  }
  if (dayOffset === 1) {
    return `明日 ${time}`;
  }

  return `${jstMonthDayFormatter.format(date)} ${time}`;
}

export function formatJstDateLabel() {
  const dataLabel = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "long",
    day: "numeric",
    weekday: "short",
  })
    .format(new Date())
    .replace(/[()]/g, " ");

  return dataLabel;
}

const jstTimeFormatter = new Intl.DateTimeFormat("ja-JP", {
  timeZone: JST_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const jstDateTimeFormatter = new Intl.DateTimeFormat("ja-JP", {
  timeZone: JST_TIME_ZONE,
  month: "long",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const jstMonthDayFormatter = new Intl.DateTimeFormat("ja-JP", {
  timeZone: JST_TIME_ZONE,
  month: "2-digit",
  day: "2-digit",
});

const jstYmdFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: JST_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** JST の暦日を、1970-01-01 からの日数にする。暦日どうしの差を取るために使う。 */
function jstDayNumber(date: Date): number {
  const [year, month, day] = jstYmdFormatter
    .format(date)
    .split("-")
    .map(Number);

  return Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1) / 86_400_000;
}

function assertValidDate(date: Date): void {
  if (Number.isNaN(date.getTime())) {
    throw new RangeError("Invalid timestamp.");
  }
}
