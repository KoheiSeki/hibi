"use client";

import type { CaptureResponse, ScenarioResponse } from "@hibi/api-client";
import { useActionState, useCallback, useState, useTransition } from "react";

import {
	acceptCaptureScenarioAction,
	deleteCaptureAction,
	retryCaptureAction,
	unmarkScenarioDoneAction,
	updateCaptureAction,
} from "./actions";
import { initialUpdateCaptureActionState } from "./capture-action-state";
import { CaptureDetailEditorView } from "./capture-detail-editor-view";
import {
	captureStatusMessage,
	isCaptureProcessing,
} from "./capture-processing-status";
import { scenarioSummary } from "./scenario-summary";
import { useCapturePolling } from "./use-capture-polling";

type CaptureDetailEditorProps = {
	captureId: string;
	defaultValue: string;
	initialStatus: string;
	timeLabel: string;
	initialClarificationText?: string | null;
	initialScenario?: ScenarioResponse | null;
};

export function CaptureDetailEditor({
	captureId,
	defaultValue,
	initialStatus,
	timeLabel,
	initialClarificationText,
	initialScenario,
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
	const [clarificationText, setClarificationText] = useState<
		string | null | undefined
	>(initialClarificationText);
	const [scenario, setScenario] = useState<ScenarioResponse | null | undefined>(
		initialScenario,
	);
	const handlePolledCapture = useCallback((capture: CaptureResponse) => {
		setStatus(capture.status);
		setClarificationText(capture.clarificationText);
		setScenario(capture.scenario);
	}, []);
	const { error: pollingError, retryPolling } = useCapturePolling({
		captureIds: isCaptureProcessing(status) ? [captureId] : [],
		onCapture: handlePolledCapture,
	});
	const [acceptPending, startAcceptTransition] = useTransition();
	const [acceptError, setAcceptError] = useState<string>();
	const [undoDonePending, startUndoDoneTransition] = useTransition();
	const [undoDoneError, setUndoDoneError] = useState<string>();
	const completed = status === "completed";
	const showClarification = completed && Boolean(clarificationText);
	const visibleScenario = completed && !showClarification ? scenario : null;

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

	function handleAccept() {
		setAcceptError(undefined);
		startAcceptTransition(async () => {
			const result = await acceptCaptureScenarioAction(captureId);
			if (result.status === "error") {
				setAcceptError(result.message);
				return;
			}
			if (result.status === "success") {
				setScenario(result.data.scenario);
			}
		});
	}

	function handleUndoDone() {
		setUndoDoneError(undefined);
		startUndoDoneTransition(async () => {
			const result = await unmarkScenarioDoneAction(captureId);
			if (result.status === "error") {
				setUndoDoneError(result.message);
				return;
			}
			if (result.status === "success") {
				setScenario(result.data.scenario);
			}
		});
	}

	const editingDisabled = status === "processing" || status === "completed";

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
			clarificationText={showClarification ? clarificationText : undefined}
			scenarioSummary={
				visibleScenario ? scenarioSummary(visibleScenario) : undefined
			}
			scenarioAccepted={visibleScenario?.status === "accepted"}
			acceptButtonProps={
				visibleScenario?.status === "proposed"
					? { onClick: handleAccept }
					: undefined
			}
			acceptPending={acceptPending}
			acceptError={acceptError}
			scenarioDone={Boolean(visibleScenario?.doneAt)}
			undoDoneButtonProps={
				visibleScenario?.doneAt ? { onClick: handleUndoDone } : undefined
			}
			undoDonePending={undoDonePending}
			undoDoneError={undoDoneError}
			editingDisabled={editingDisabled}
			updatePending={pending}
			updateFormProps={{ action: formAction }}
			deletePending={deletePending}
			deleteButtonProps={{ onClick: handleDelete }}
		/>
	);
}
