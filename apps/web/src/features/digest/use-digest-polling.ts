"use client";

import type { DigestReportResponse } from "@hibi/api-client";
import { useEffect, useRef, useState } from "react";

import { getLatestDigestReportAction } from "./actions";

const DIGEST_POLLING_INTERVAL_MS = 3000;

type UseDigestPollingOptions = {
	report: DigestReportResponse;
	onReport: (report: DigestReportResponse) => void;
};

type UseDigestPollingResult = {
	error?: string;
};

/**
 * pending のダイジェストを、3 秒おきに読み直す。
 *
 * API には ID で 1 件を読む endpoint がないので、同じ種類の最新を読む。返った行は、
 * `onReport` に渡す。pending のあいだだけ読み続け、ready か failed になったら止まる。
 * 失敗したときは、読み続けても直らないことが多いので止めて、メッセージを返す。
 * `useCapturePolling` と同じ流儀にしている。
 *
 * @param options.report - 表示しているレポート。`status` が pending のときだけ読む
 * @param options.onReport - 読み直した行を受け取る
 * @returns 読み直しに失敗したときの `error`
 */
export function useDigestPolling({
	report,
	onReport,
}: UseDigestPollingOptions): UseDigestPollingResult {
	const [error, setError] = useState<string>();
	const onReportRef = useRef(onReport);
	const stoppedRef = useRef(false);
	const { id, kind, status } = report;

	useEffect(() => {
		onReportRef.current = onReport;
	}, [onReport]);

	useEffect(() => {
		if (status !== "pending" || stoppedRef.current) {
			return;
		}

		let active = true;
		let timer: ReturnType<typeof setTimeout> | undefined;

		async function poll() {
			try {
				const result = await getLatestDigestReportAction(kind);
				if (!active) {
					return;
				}
				if (result.status === "error") {
					stoppedRef.current = true;
					setError(result.message);
					return;
				}
				if (result.status !== "success" || result.data === null) {
					stoppedRef.current = true;
					return;
				}

				onReportRef.current(result.data);
				if (result.data.status === "pending") {
					timer = setTimeout(poll, DIGEST_POLLING_INTERVAL_MS);
				}
			} catch {
				if (!active) {
					return;
				}
				stoppedRef.current = true;
				setError("状態を取得できませんでした。");
			}
		}

		timer = setTimeout(poll, DIGEST_POLLING_INTERVAL_MS);

		return () => {
			active = false;
			if (timer) {
				clearTimeout(timer);
			}
		};
	}, [id, kind, status]);

	return { error };
}
