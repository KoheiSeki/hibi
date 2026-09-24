import "server-only";

import { getCurrentUser, UserResponse } from "@hibi/api-client";
import { ApiResult, normalizeGeneratedResult } from "./request-api";
import { createClient } from "../auth/server";

export async function getCurrentUserFromApi(): Promise<
	ApiResult<UserResponse>
> {
	const supabase = await createClient();
	const {
		data: { session },
	} = await supabase.auth.getSession();

	const accessToken = session?.access_token;
	// 未ログインの場合
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

	const result = await getCurrentUser({ baseUrl, auth: accessToken });

	return normalizeGeneratedResult<UserResponse>(result);
}
