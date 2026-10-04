import "server-only";

import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { listCapturesFromApi } from "@/lib/api/capture";

import { CaptureEmptyState } from "./capture-empty-state";
import type { CaptureListItemView } from "./capture-list";
import { CaptureListPager } from "./capture-list-pager";
import { mapCaptureResponsesToListItemViews } from "./map-capture-to-list-item";

export async function CaptureListSection(): Promise<ReactNode> {
	const result = await listCapturesFromApi();
	if (!result.ok) {
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		return <ApiErrorMessage error={result.error} />;
	}

	const captures = result.data.data;
	const meta = result.data.meta;
	if (captures.length === 0) {
		return <CaptureEmptyState />;
	}
	const items: CaptureListItemView[] =
		mapCaptureResponsesToListItemViews(captures);

	return (
		<CaptureListPager
			initialItems={items}
			initialNextCursor={meta.nextCursor}
			initialHasNextPage={meta.hasNextPage}
		/>
	);
}
