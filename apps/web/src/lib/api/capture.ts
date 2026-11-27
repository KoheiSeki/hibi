import "server-only";

import {
	type ApiResponseWithMetaListCaptureResponseCursorMeta,
	type CaptureResponse,
	acceptCaptureScenario,
	createCapture,
	deleteCapture,
	getCapture,
	listCaptures,
	listTodayCaptures,
	markCaptureScenarioDone,
	retryCapture,
	searchCaptures,
	unmarkCaptureScenarioDone,
	updateCapture,
} from "@hibi/api-client";
import {
	ApiResult,
	normalizeGeneratedEmptyResult,
	normalizeGeneratedEnvelopeResult,
	normalizeGeneratedResult,
} from "./request-api";
import { getServerApiContext } from "./server-context";
import { CaptureSearch } from "./capture-search";

type ListCapturesParams = {
	limit?: number;
	cursor?: string;
};

type ListTodayCapturesParams = {
	limit?: number;
};

/**
 * 完了した記録を、自分の分だけ検索する。
 *
 * @param search.q - 検索語。1 文字以上 200 文字以下。
 * @param search.mode - `keyword` は本文の語の重なり、`semantic` は意味の近さで選ぶ。
 * @returns 近い順の記録。最大 20 件で、見つからなければ空の配列。
 */
export async function searchCapturesFromApi({
	q,
	mode,
}: CaptureSearch): Promise<ApiResult<CaptureResponse[]>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await searchCaptures({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		query: {
			q,
			mode,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 記録を 1 件取得する。
 *
 * @param captureId - 取得する記録の id。
 * @returns 記録。シナリオと聞き返し文があれば含む。無ければ not-found の失敗。
 */
export async function getCaptureFromApi(
	captureId: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await getCapture({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 今日やることを、優先度の高い順に取得する。
 *
 * @param params.limit - 取得する最大件数。省略すると API の既定値になる。
 * @returns 優先度の高い順の記録。シナリオを含む。
 */
export async function listTodayCapturesFromApi({
	limit,
}: ListTodayCapturesParams = {}): Promise<ApiResult<CaptureResponse[]>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await listTodayCaptures({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		query: {
			limit,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 自分の記録を、新しい順に 1 ページ取得する。
 *
 * @param params.limit - 1 ページの件数。既定は 20。
 * @param params.cursor - 前のページの `meta.nextCursor`。省略すると先頭のページ。
 * @returns 記録と、続きを読むための `meta`(`nextCursor`、`hasNextPage`)。
 */
export async function listCapturesFromApi({
	limit = 20,
	cursor,
}: ListCapturesParams = {}): Promise<
	ApiResult<ApiResponseWithMetaListCaptureResponseCursorMeta>
> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await listCaptures({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		query: {
			limit,
			cursor,
		},
	});
	return normalizeGeneratedEnvelopeResult(result);
}

/**
 * 記録を作り、AI による処理を予約する。
 *
 * 同じ冪等キーと本文の再送は、新しく作らず、既存の記録を返す。
 *
 * @param rawText - 記録の本文。
 * @param idempotencyKey - 作成の冪等キー。再送のときは同じ値を使う。
 * @returns 作成した記録。status は pending。
 */
export async function createCaptureFromApi(
	rawText: string,
	idempotencyKey: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await createCapture({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		body: {
			rawText,
		},
		headers: {
			"Idempotency-Key": idempotencyKey,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 記録の本文を更新する。更新できるのは pending と failed の記録だけ。
 *
 * @param captureId - 更新する記録の id。
 * @param rawText - 新しい本文。
 * @returns 更新後の記録。
 */
export async function updateCaptureFromApi(
	captureId: string,
	rawText: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await updateCapture({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		body: {
			rawText,
		},
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * failed の記録を、もう一度処理に回す。
 *
 * @param captureId - やり直す記録の id。
 * @returns 処理の世代が進み、status が pending に戻った記録。
 */
export async function retryCaptureFromApi(
	captureId: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await retryCapture({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 提案されたシナリオを、確認して accepted にする。
 *
 * @param captureId - シナリオを確認する記録の id。
 * @returns 更新後の記録。
 */
export async function acceptCaptureScenarioFromApi(
	captureId: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await acceptCaptureScenario({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 記録のシナリオを、完了にする。
 *
 * 繰り返し呼んでも結果は同じで、最初の完了時刻が残る。
 *
 * @param captureId - 完了にする記録の id。
 * @returns 更新後の記録。シナリオの `doneAt` が入る。
 */
export async function markCaptureScenarioDoneFromApi(
	captureId: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await markCaptureScenarioDone({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}

/**
 * 記録を削除する。シナリオと embedding も一緒に消える。
 *
 * @param captureId - 削除する記録の id。
 * @returns 成功したときは値を持たない。
 */
export async function deleteCaptureFromApi(
	captureId: string,
): Promise<ApiResult<void>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await deleteCapture({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedEmptyResult(result);
}

/**
 * 記録のシナリオを、未完了に戻す。
 *
 * 完了にしていない記録に呼んでも、エラーにならない。
 *
 * @param captureId - 未完了に戻す記録の id。
 * @returns 更新後の記録。シナリオの `doneAt` は `null` になる。
 */
export async function unmarkCaptureScenarioDoneFromApi(
	captureId: string,
): Promise<ApiResult<CaptureResponse>> {
	const context = await getServerApiContext();
	if (!context.ok) {
		return context;
	}

	const result = await unmarkCaptureScenarioDone({
		baseUrl: context.baseUrl,
		auth: context.accessToken,
		path: {
			capture_id: captureId,
		},
	});
	return normalizeGeneratedResult(result);
}
