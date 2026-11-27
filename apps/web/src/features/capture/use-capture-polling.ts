"use client";

import type { CaptureResponse } from "@hibi/api-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { getCaptureAction } from "./actions";

const CAPTURE_POLLING_INTERVAL_MS = 3000;

type UseCapturePollingOptions = {
	captureIds: readonly string[];
	onCapture: (capture: CaptureResponse) => void;
};

type UseCapturePollingResult = {
	error?: string;
	retryPolling: () => void;
};

export function useCapturePolling({
	captureIds,
	onCapture,
}: UseCapturePollingOptions): UseCapturePollingResult {
	const [error, setError] = useState<string>();
	const [restartToken, setRestartToken] = useState(0);
	const onCaptureRef = useRef(onCapture);
	const stoppedRef = useRef(false);
	const retryImmediatelyRef = useRef(false);
	const captureIdsKey = JSON.stringify(captureIds);

	useEffect(() => {
		onCaptureRef.current = onCapture;
	}, [onCapture]);

	const retryPolling = useCallback(() => {
		stoppedRef.current = false;
		retryImmediatelyRef.current = true;
		setError(undefined);
		setRestartToken((current) => current + 1);
	}, []);

	useEffect(() => {
		const ids = JSON.parse(captureIdsKey) as string[];
		if (ids.length === 0 || stoppedRef.current) {
			return;
		}

		let active = true;
		let timer: ReturnType<typeof setTimeout> | undefined;

		async function poll() {
			try {
				const results = await Promise.all(
					ids.map((captureId) => getCaptureAction(captureId)),
				);
				if (!active) {
					return;
				}

				const failure = results.find((result) => result.status === "error");
				if (failure?.status === "error") {
					stoppedRef.current = true;
					setError(failure.message);
					return;
				}

				for (const result of results) {
					if (result.status === "success") {
						onCaptureRef.current(result.data);
					}
				}
				timer = setTimeout(poll, CAPTURE_POLLING_INTERVAL_MS);
			} catch {
				if (!active) {
					return;
				}
				stoppedRef.current = true;
				setError("状態を取得できませんでした。");
			}
		}

		const delay = retryImmediatelyRef.current
			? 0
			: CAPTURE_POLLING_INTERVAL_MS;
		retryImmediatelyRef.current = false;
		timer = setTimeout(poll, delay);

		return () => {
			active = false;
			if (timer) {
				clearTimeout(timer);
			}
		};
	}, [captureIdsKey, restartToken]);

	return { error, retryPolling };
}
