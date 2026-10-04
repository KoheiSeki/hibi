import "server-only";

import {
	type ApiResponseWithMetaListCaptureResponseCursorMeta,
	type CaptureResponse,
	createCapture,
	listCaptures,
} from "@hibi/api-client";
import {
	ApiResult,
	normalizeGeneratedEnvelopeResult,
	normalizeGeneratedResult,
} from "./request-api";
import { getServerApiContext } from "./server-context";

type ListCapturesParams = {
	limit?: number;
	cursor?: string;
};

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
			idempotencyKey,
		},
	});
	return normalizeGeneratedResult(result);
}
