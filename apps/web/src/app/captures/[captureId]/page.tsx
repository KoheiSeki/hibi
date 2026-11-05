import type { ReactNode } from "react";
import { notFound, redirect } from "next/navigation";

import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { CaptureDetailEditor } from "@/features/capture/capture-detail-editor";
import { getCaptureFromApi } from "@/lib/api/capture";
import { requireUser } from "@/lib/auth/require-user";
import { formatJstDateTime } from "@/lib/date-time";

type CaptureDetailPageProps = {
	params: Promise<{ captureId: string }>;
};

export default async function CaptureDetailPage({
	params,
}: CaptureDetailPageProps): Promise<ReactNode> {
	await requireUser();

	const { captureId } = await params;
	const result = await getCaptureFromApi(captureId);
	if (!result.ok) {
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		if (
			result.error.kind === "problem" &&
			result.error.problem.status === 404
		) {
			notFound();
		}

		return <ApiErrorMessage error={result.error} />;
	}

	return (
		<main className="mx-auto w-full max-w-2xl">
			<CaptureDetailEditor
				captureId={result.data.id}
				defaultValue={result.data.rawText}
				initialStatus={result.data.status}
				timeLabel={formatJstDateTime(result.data.createdAt)}
				initialClarificationText={result.data.clarificationText}
				initialScenario={result.data.scenario}
			/>
		</main>
	);
}
