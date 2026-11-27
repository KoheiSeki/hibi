import { type CaptureResponse } from "@hibi/api-client";
import { type CaptureListItemView } from "./capture-list";
import { formatJstTime } from "@/lib/date-time";

export function mapCaptureResponsesToListItemViews(
	captures: readonly CaptureResponse[],
): CaptureListItemView[] {
	return captures.map(mapCaptureResponseToListItemView);
}

function mapCaptureResponseToListItemView(capture: CaptureResponse) {
	return {
		id: capture.id,
		href: `/captures/${capture.id}`,
		rawText: capture.rawText,
		status: capture.status,
		dateTime: capture.createdAt,
		timeLabel: formatJstTime(capture.createdAt),
	};
}
