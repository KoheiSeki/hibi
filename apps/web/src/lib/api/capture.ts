import "server-only";

import {
	type ApiResponseWithMetaListCaptureResponseCursorMeta,
	listCaptures,
} from "@hibi/api-client";
import { createClient } from "../auth/server";
import { ApiResult, normalizeGeneratedEnvelopeResult } from "./request-api";

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
	const supabase = await createClient();
	const {
		data: { session },
	} = await supabase.auth.getSession();

	const accessToken = session?.access_token;
	if (!accessToken) {
		return {
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		};
	}

	const baseUrl = process.env.HIBI_API_BASE_URL;
	if (!baseUrl) {
		throw new Error("HIBI_API_BASE_URL is not configured.");
	}
	const result = await listCaptures({
		baseUrl,
		auth: accessToken,
		query: {
			limit,
			cursor,
		},
	});
	return normalizeGeneratedEnvelopeResult(result);
}
