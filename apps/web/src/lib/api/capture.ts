import "server-only";

import {
	type ApiResponseWithMetaListCaptureResponseCursorMeta,
	type CaptureResponse,
	createCapture,
	deleteCapture,
	getCapture,
	listCaptures,
	retryCapture,
	updateCapture,
} from "@hibi/api-client";
import {
	ApiResult,
	normalizeGeneratedEmptyResult,
	normalizeGeneratedEnvelopeResult,
	normalizeGeneratedResult,
} from "./request-api";
import { getServerApiContext } from "./server-context";

type ListCapturesParams = {
	limit?: number;
	cursor?: string;
};

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
			"Idempotency-Key": idempotencyKey,
		},
	});
	return normalizeGeneratedResult(result);
}

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
