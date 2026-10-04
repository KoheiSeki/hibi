"use client";

import { Button } from "@/components/ui/button";

import {
  CaptureList,
  type CaptureListItemView,
} from "./capture-list";

type CaptureListPagerProps = {
  initialItems: readonly CaptureListItemView[];
  initialNextCursor: string | null;
  initialHasNextPage: boolean;
};

export function CaptureListPager({
  initialItems,
  initialNextCursor,
  initialHasNextPage,
}: CaptureListPagerProps) {
  const hasNextPage = initialHasNextPage && initialNextCursor !== null;

  return (
    <div>
      <CaptureList items={initialItems} />

      {hasNextPage ? (
        <div className="flex justify-center py-6">
          <Button
            type="button"
            variant="outline"
            className="h-11 rounded-full border-[#BFC8D3] bg-transparent px-6 text-[#1A1D23]"
          >
            さらに表示
          </Button>
        </div>
      ) : null}
    </div>
  );
}
