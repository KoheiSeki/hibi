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

function assertValidDate(date: Date): void {
	if (Number.isNaN(date.getTime())) {
		throw new RangeError("Invalid timestamp.");
	}
}
