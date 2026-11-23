"use server";

import {
	listDigestReportsFromApi,
	retryDigestReportFromApi,
} from "@/lib/api/digest";
import type {
	GetLatestDigestReportActionState,
	RetryDigestReportActionState,
} from "./digest-action-state";
import { toActionErrorState } from "@/lib/api/action-error";
import { revalidatePath } from "next/cache";

/**
 * 作れなかったダイジェストを、もう一度作るよう API に頼む。
 *
 * 成功すると、レポートは pending に戻る。`/captures/digest` を revalidate して、
 * 次に表示するときに新しい状態を読むようにする。存在しないレポート(404)や、
 * まだ作っている途中のレポート(409)は、画面全体を not found にせず、
 * カードの下に出すエラーの state として返す。
 *
 * @param reportId - もう一度作るレポートの ID。client から届く値なので、
 *   空の文字列は API を呼ばずにエラーにする
 * @returns 成功すると、pending に戻ったレポートを持つ state
 */
export async function retryDigestReportAction(
	reportId: string,
): Promise<RetryDigestReportActionState> {
	if (typeof reportId !== "string" || reportId.trim().length === 0) {
		return {
			status: "error",
			message: "もう一度作れませんでした。",
		};
	}
	const result = await retryDigestReportFromApi(reportId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	revalidatePath("/captures/digest");

	return {
		status: "success",
		data: result.data,
		message: "もう一度作っています。",
	};
}

/**
 * 指定した種類の、いちばん新しいダイジェストを読む。
 *
 * pending のカードが、ready か failed になるまで polling するために使う。
 * API には ID で 1 件を読む endpoint がないので、種類ごとの一覧を 1 件だけ読む。
 * 読むだけなので revalidate しない。
 *
 * @param kind - 読むレポートの種類。朝のダイジェストは `daily`、週次レビューは `weekly`
 * @returns 成功すると、いちばん新しいレポートを持つ state。その種類のレポートが
 *   まだなければ、`data` は `null`
 */
export async function getLatestDigestReportAction(
	kind: "daily" | "weekly",
): Promise<GetLatestDigestReportActionState> {
	const result = await listDigestReportsFromApi({ kind, limit: 1 });
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	return {
		status: "success",
		data: result.data[0] ?? null,
	};
}
