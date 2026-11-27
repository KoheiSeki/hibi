import "server-only";

import {
	listDigestReports,
	retryDigestReport,
	type DigestReportResponse,
} from "@hibi/api-client";
import { ApiResult, normalizeGeneratedResult } from "./request-api";
import { getServerApiContext } from "./server-context";

type ListDigestReportsParams = {
	kind?: "daily" | "weekly";
	fromDate?: string;
	limit?: number;
};

/**
 * 自分の朝のダイジェストと週次レビューを、期間の日付の新しい順に取得する。
 *
 * 作っている途中(pending)と、失敗した行(failed)も含む。種類ごとの最新を読むときは、
 * `kind` を指定して `limit: 1` にする。種類を分けずに読むと、毎日の daily に押されて、
 * 期間の日付が古い weekly が入らないことがある。
 *
 * @param params.kind - `daily` か `weekly`。省くと両方。
 * @param params.fromDate - `periodStart` の下限(YYYY-MM-DD)で、その日を含む。利用者の
 * timezone での暦日。作った日ではなく、期間の日付で絞る。省くと下限なし。
 * @param params.limit - 取得する最大件数。1 以上 30 以下で、省くと API の既定値(7)になる。
 * @returns 期間の日付(`periodStart`)の新しい順の行。無ければ空の配列。
 */
export async function listDigestReportsFromApi({
	kind,
	fromDate,
	limit,
}: ListDigestReportsParams = {}): Promise<ApiResult<DigestReportResponse[]>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await listDigestReports({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		query: {
			kind,
			fromDate,
			limit,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 失敗したダイジェストか週次レビューを、もう一度作るよう予約する。
 *
 * API は 202 を返し、中身は後で作られる。返る行は pending で、`content` と `errorCode` は
 * null。ready になったかは、`listDigestReportsFromApi` で、その種類の最新を読み直して
 * 確かめる。1 件だけを読む API は無い。
 *
 * failed でない行(pending か ready)は 409、自分の行でない、または無ければ 404 の失敗に
 * なる。retry を続けて送ると、2 回目からは pending なので 409 になる。
 *
 * @param reportId - もう一度作る行の id。
 * @returns pending に戻った行。
 */
export async function retryDigestReportFromApi(
	reportId: string,
): Promise<ApiResult<DigestReportResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await retryDigestReport({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			report_id: reportId,
		},
	});
	return normalizeGeneratedResult(result);
}
