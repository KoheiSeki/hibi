import "server-only";

import { createClient } from "../auth/server";

type ServerApiContext =
	| {
			ok: true;
			baseUrl: string;
			accessToken: string;
	  }
	| {
			ok: false;
			error: {
				kind: "unauthenticated";
				message: string;
			};
	  };

export async function getServerApiContext(): Promise<ServerApiContext> {
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

	return {
		ok: true,
		baseUrl,
		accessToken,
	};
}
