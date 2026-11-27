/** 朝のダイジェストに並ぶ、今日やることの 1 行。 */
export type DailyDigestItem = {
	captureId: string;
	title: string;
	dueAt: string | null;
};

/** 朝のダイジェスト(`daily-digest-v1`)の中身。 */
export type DailyDigestContent = {
	items: DailyDigestItem[];
	overdueCount: number;
	dueTodayCount: number;
	doneYesterdayCount: number;
};

/** 週次レビュー(`weekly-review-v1`)の中身。 */
export type WeeklyReviewContent = {
	stats: {
		capturedCount: number;
		doneCount: number;
		openCount: number;
		overdueCount: number;
	};
	summary: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isCount(value: unknown): value is number {
	return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

function isDailyDigestItem(value: unknown): value is DailyDigestItem {
	return (
		isRecord(value) &&
		typeof value.captureId === "string" &&
		typeof value.title === "string" &&
		(value.dueAt === null || typeof value.dueAt === "string")
	);
}

/**
 * API の `content` を、朝のダイジェストの中身として読む。
 *
 * 生成される client では `content` の型が `{ [key: string]: unknown }` なので、
 * 画面で使う前に形を確かめる。形が違うときは、壊れた表示を出さないよう `null` を返す。
 *
 * @param content - `DigestReportResponse` の `content`
 * @returns 形が合えば中身、合わなければ `null`
 */
export function parseDailyDigestContent(
	content: unknown,
): DailyDigestContent | null {
	if (
		!isRecord(content) ||
		!Array.isArray(content.items) ||
		!content.items.every(isDailyDigestItem) ||
		!isCount(content.overdueCount) ||
		!isCount(content.dueTodayCount) ||
		!isCount(content.doneYesterdayCount)
	) {
		return null;
	}

	return {
		items: content.items,
		overdueCount: content.overdueCount,
		dueTodayCount: content.dueTodayCount,
		doneYesterdayCount: content.doneYesterdayCount,
	};
}

/**
 * API の `content` を、週次レビューの中身として読む。
 *
 * `parseDailyDigestContent` と同じく、形が違うときは `null` を返す。
 *
 * @param content - `DigestReportResponse` の `content`
 * @returns 形が合えば中身、合わなければ `null`
 */
export function parseWeeklyReviewContent(
	content: unknown,
): WeeklyReviewContent | null {
	if (!isRecord(content) || typeof content.summary !== "string") {
		return null;
	}

	const { stats } = content;
	if (
		!isRecord(stats) ||
		!isCount(stats.capturedCount) ||
		!isCount(stats.doneCount) ||
		!isCount(stats.openCount) ||
		!isCount(stats.overdueCount)
	) {
		return null;
	}

	return {
		stats: {
			capturedCount: stats.capturedCount,
			doneCount: stats.doneCount,
			openCount: stats.openCount,
			overdueCount: stats.overdueCount,
		},
		summary: content.summary,
	};
}

const periodDateFormatter = new Intl.DateTimeFormat("ja-JP", {
	month: "long",
	day: "numeric",
	weekday: "short",
	timeZone: "UTC",
});

/**
 * `YYYY-MM-DD` の期間の始まりを、`11月22日(日)` の形にする。
 *
 * `periodStart` は、ユーザーの timezone での暦日で、時刻を持たない。UTC の 0 時として
 * 読み、UTC で書き出すと、server と client のどちらで描いても同じ日付になる。
 *
 * @param periodStart - API の `periodStart`
 * @returns 月、日、曜日の文字列。読めない値なら、受け取った文字列をそのまま返す
 */
export function formatPeriodStart(periodStart: string): string {
	const date = new Date(`${periodStart}T00:00:00Z`);
	if (Number.isNaN(date.getTime())) {
		return periodStart;
	}

	return periodDateFormatter.format(date);
}
