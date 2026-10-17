import { ReactNode, Suspense } from "react";
import { CapturePageFrame } from "@/features/capture/capture-page-frame";
import { CaptureComposer } from "@/features/capture/capture-composer";
import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";
import { formatJstDateLabel } from "@/lib/date-time";
import { CaptureListSection } from "@/features/capture/capture-list-section";
import { requireUser } from "@/lib/auth/require-user";

export default async function CapturePage(): Promise<ReactNode> {
	await requireUser();

	return (
		<CapturePageFrame
			dateLabel={formatJstDateLabel()}
			composer={<CaptureComposer />}
		>
			<Suspense fallback={<CaptureListSkeleton />}>
				<CaptureListSection />
			</Suspense>
		</CapturePageFrame>
	);
}
