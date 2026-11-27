import "server-only";

import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { searchCapturesFromApi } from "@/lib/api/capture";
import type { CaptureSearch } from "@/lib/api/capture-search";

import { CaptureList } from "./capture-list";
import { CaptureSearchEmptyState } from "./capture-search-empty-state";
import { mapCaptureResponsesToListItemViews } from "./map-capture-to-list-item";

/**
 * 検索 API を呼び、今の一覧行で結果を出す。
 *
 * 結果は最大 20 件でカーソルが無く、completed だけなので、
 * pager も polling も使わない。未認証なら /login へ送る。
 *
 * @param search - 正規化済みの検索条件。
 */
export async function CaptureSearchResultsSection({
	q,
	mode,
}: CaptureSearch): Promise<ReactNode> {
	const result = await searchCapturesFromApi({ q, mode });
	if (!result.ok) {
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		return <ApiErrorMessage error={result.error} />;
	}

	if (result.data.length === 0) {
		return <CaptureSearchEmptyState />;
	}

	return (
		<CaptureList items={mapCaptureResponsesToListItemViews(result.data)} />
	);
}
