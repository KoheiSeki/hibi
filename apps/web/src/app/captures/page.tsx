import { ReactNode, Suspense } from "react";
import { CapturePageFrame } from "@/features/capture/capture-page-frame";
import { CaptureComposer } from "@/features/capture/capture-composer";
import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";
import { formatJstDateLabel } from "@/lib/date-time";
import { CaptureListSection } from "@/features/capture/capture-list-section";
import { CaptureSearchForm } from "@/features/capture/capture-search-form";
import { parseCaptureSearchParams } from "@/features/capture/capture-search-params";
import { CaptureSearchResultsSection } from "@/features/capture/capture-search-results-section";
import { requireUser } from "@/lib/auth/require-user";

type CapturePageProps = {
	searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

/** 検索中にだけ出す。検索語を変えたとき fallback を出し直すため、呼び出し側で key を付ける。 */
function CaptureSearchPending(): ReactNode {
	return (
		<p role="status" className="py-6 text-sm text-[#5A6A62]">
			検索しています
		</p>
	);
}

export default async function CapturePage({
	searchParams,
}: CapturePageProps): Promise<ReactNode> {
	await requireUser();
	const search = parseCaptureSearchParams(await searchParams);

	return (
		<CapturePageFrame
			dateLabel={formatJstDateLabel()}
			composer={<CaptureComposer />}
			search={
				<CaptureSearchForm
					defaultQuery={search?.q ?? ""}
					defaultMode={search?.mode ?? "keyword"}
				/>
			}
		>
			{search ? (
				<Suspense
					key={`${search.mode}:${search.q}`}
					fallback={<CaptureSearchPending />}
				>
					<CaptureSearchResultsSection q={search.q} mode={search.mode} />
				</Suspense>
			) : (
				<Suspense fallback={<CaptureListSkeleton />}>
					<CaptureListSection />
				</Suspense>
			)}
		</CapturePageFrame>
	);
}
