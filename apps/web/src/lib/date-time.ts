const JST_TIME_ZONE = "Asia/Tokyo";

export function formatJstTime(timestamp: string): string {
	const date = new Date(timestamp);

	if (Number.isNaN(date.getTime())) {
		throw new RangeError("Invalid timestamp.");
	}

	return jstTimeFormatter.format(date);
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
