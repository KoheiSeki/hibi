"use client";

import { useActionState, useState, useTransition } from "react";

import { deleteCaptureAction, updateCaptureAction } from "./actions";
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
	const [deletePending, startDeleteTransition] = useTransition();
	const [deleteError, setDeleteError] = useState<string>();

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

	return (
		<CaptureDetailEditorView
			defaultValue={defaultValue}
			timeLabel={timeLabel}
			fieldError={
				state.status === "error" ? state.fieldErrors?.rawText : undefined
			}
			message={state.status === "idle" ? undefined : state.message}
			errorMessage={deleteError}
			updatePending={pending}
			updateFormProps={{ action: formAction }}
			deletePending={deletePending}
			deleteButtonProps={{ onClick: handleDelete }}
		/>
	);
}
