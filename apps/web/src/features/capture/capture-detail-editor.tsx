"use client";

import { useActionState, useCallback, useState, useTransition } from "react";

import {
	deleteCaptureAction,
	retryCaptureAction,
	updateCaptureAction,
} from "./actions";
import { initialUpdateCaptureActionState } from "./capture-action-state";
import { CaptureDetailEditorView } from "./capture-detail-editor-view";
import {
	captureStatusMessage,
	isCaptureProcessing,
} from "./capture-processing-status";
import { useCapturePolling } from "./use-capture-polling";

type CaptureDetailEditorProps = {
	captureId: string;
	defaultValue: string;
	initialStatus: string;
	timeLabel: string;
};

export function CaptureDetailEditor({
	captureId,
	defaultValue,
	initialStatus,
	timeLabel,
}: CaptureDetailEditorProps) {
	const [status, setStatus] = useState(initialStatus);
	const [state, formAction, pending] = useActionState(
		updateCaptureAction.bind(null, captureId),
		initialUpdateCaptureActionState,
	);
	const [deletePending, startDeleteTransition] = useTransition();
	const [deleteError, setDeleteError] = useState<string>();
	const [retryPending, startRetryTransition] = useTransition();
	const [retryError, setRetryError] = useState<string>();
	const handlePolledCapture = useCallback(
		(capture: { status: string }) => setStatus(capture.status),
		[],
	);
	const {
		error: pollingError,
		retryPolling,
	} = useCapturePolling({
		captureIds: isCaptureProcessing(status) ? [captureId] : [],
		onCapture: handlePolledCapture,
	});
	const editingDisabled = status === "processing" || status === "completed";

	function handleDelete() {
		if (!window.confirm("この記録を削除しますか？")) {
			return;
		}

		setDeleteError(undefined);
		startDeleteTransition(async () => {
			const result = await deleteCaptureAction(captureId);
			if (result.status === "error") {
				setDeleteError(result.message);
			}
		});
	}

	function handleRetry() {
		setRetryError(undefined);
		startRetryTransition(async () => {
			const result = await retryCaptureAction(captureId);
			if (result.status === "error") {
				setRetryError(result.message);
				return;
			}
			if (result.status === "success") {
				setStatus(result.data.status);
			}
		});
	}

	return (
		<CaptureDetailEditorView
			defaultValue={defaultValue}
			timeLabel={timeLabel}
			statusMessage={captureStatusMessage(status)}
			fieldError={
				state.status === "error" ? state.fieldErrors?.rawText : undefined
			}
			message={state.status === "idle" ? undefined : state.message}
			errorMessage={deleteError}
			pollingError={pollingError}
			pollingRetryButtonProps={{ onClick: retryPolling }}
			retryError={retryError}
			retryPending={retryPending}
			retryButtonProps={
				status === "failed" ? { onClick: handleRetry } : undefined
			}
			editingDisabled={editingDisabled}
			updatePending={pending}
			updateFormProps={{ action: formAction }}
			deletePending={deletePending}
			deleteButtonProps={{ onClick: handleDelete }}
		/>
	);
}
