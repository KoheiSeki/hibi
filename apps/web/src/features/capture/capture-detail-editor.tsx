"use client";

import { useActionState } from "react";

import { updateCaptureAction } from "./actions";
import { initialUpdateCaptureActionState } from "./capture-action-state";
import { CaptureDetailEditorView } from "./capture-detail-editor-view";

type CaptureDetailEditorProps = {
	captureId: string;
	defaultValue: string;
	timeLabel: string;
};

export function CaptureDetailEditor({
	captureId,
	defaultValue,
	timeLabel,
}: CaptureDetailEditorProps) {
	const [state, formAction, pending] = useActionState(
		updateCaptureAction.bind(null, captureId),
		initialUpdateCaptureActionState,
	);

	return (
		<CaptureDetailEditorView
			defaultValue={defaultValue}
			timeLabel={timeLabel}
			fieldError={
				state.status === "error" ? state.fieldErrors?.rawText : undefined
			}
			message={state.status === "idle" ? undefined : state.message}
			updatePending={pending}
			updateFormProps={{ action: formAction }}
		/>
	);
}
