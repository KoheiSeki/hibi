export function isCaptureProcessing(status: string): boolean {
	return status === "pending" || status === "processing";
}

export function captureStatusMessage(status: string): string | undefined {
	if (isCaptureProcessing(status)) {
		return "整えています";
	}
	if (status === "failed") {
		return "やり直せます";
	}
	return undefined;
}
