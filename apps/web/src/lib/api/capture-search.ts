import { SearchCapturesData } from "@hibi/api-client";

export type CaptureSearchMode = NonNullable<
	SearchCapturesData["query"]["mode"]
>;

export type CaptureSearch = { q: string; mode: CaptureSearchMode };
