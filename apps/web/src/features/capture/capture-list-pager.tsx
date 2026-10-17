"use client";

import { Button } from "@/components/ui/button";

import { CaptureList, type CaptureListItemView } from "./capture-list";
import { useState, useTransition } from "react";
import { listCapturesAction } from "./actions";
import { mapCaptureResponsesToListItemViews } from "./map-capture-to-list-item";

type CaptureListPagerProps = {
	initialItems: CaptureListItemView[];
	initialNextCursor: string | null;
	initialHasNextPage: boolean;
};

export function CaptureListPager({
	initialItems,
	initialNextCursor,
	initialHasNextPage,
}: CaptureListPagerProps) {
	const [items, setItems] = useState<CaptureListItemView[]>(initialItems);
	const [nextCursor, setNextCursor] = useState<string | null>(
		initialNextCursor,
	);
	const [hasNextPage, setHasNextPage] = useState<boolean>(initialHasNextPage);
	const [error, setError] = useState<string | null>(null);
	const [pending, startTransition] = useTransition();

	function handleLoadMore() {
		if (pending || !hasNextPage || !nextCursor) {
			return;
		}

		setError(null);

		startTransition(async () => {
			const result = await listCapturesAction(nextCursor);
			if (result.status === "error") {
				setError(result.message);
				return;
			}

			if (result.status !== "success") {
				return;
			}

			const newItems = mapCaptureResponsesToListItemViews(result.data.data);

			setItems((current) => {
				const existingIds = new Set(current.map(({ id }) => id));

				return [
					...current,
					...newItems.filter(({ id }) => !existingIds.has(id)),
				];
			});

			setNextCursor(result.data.meta.nextCursor);
			setHasNextPage(result.data.meta.hasNextPage);
		});
	}

	return (
		<div>
			<CaptureList items={items} />

			{error ? (
				<p
					id="capture-list-load-more-error"
					className="mt-5 text-center text-sm text-destructive"
					role="alert"
				>
					{error}
				</p>
			) : null}

			{hasNextPage ? (
				<div className="flex justify-center py-6">
					<Button
						type="button"
						variant="outline"
						onClick={handleLoadMore}
						disabled={pending}
						aria-describedby={
							error ? "capture-list-load-more-error" : undefined
						}
						className="h-11 rounded-full border-[#D5E3D9] bg-[#F7FBF8] px-6 text-[#15201A] hover:border-[#1E6B43] hover:text-[#1E6B43]"
					>
						{pending ? "読み込んでいます" : "さらに表示"}
					</Button>
				</div>
			) : null}
		</div>
	);
}
