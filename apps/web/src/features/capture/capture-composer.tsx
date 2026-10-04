"use client";

import {
	useActionState,
	useCallback,
	useEffect,
	useRef,
	useState,
} from "react";

import { createCaptureAction } from "./actions";
import { initialCreateCaptureActionState } from "./capture-action-state";
import type { CreateCaptureActionState } from "./capture-action-state";
import { CaptureComposerView } from "./capture-composer-view";
import { createIdempotencyKeyManager } from "./idempotency-key-manager";

export function CaptureComposer() {
	const [idempotencyKeyManager] = useState(createIdempotencyKeyManager);
	const formRef = useRef<HTMLFormElement>(null);
	const createWithIdempotencyKey = useCallback(
		async (
			previousState: CreateCaptureActionState,
			formData: FormData,
		): Promise<CreateCaptureActionState> => {
			idempotencyKeyManager.applyTo(formData);
			return createCaptureAction(previousState, formData);
		},
		[idempotencyKeyManager],
	);
	const [state, formAction, pending] = useActionState(
		createWithIdempotencyKey,
		initialCreateCaptureActionState,
	);

	useEffect(() => {
		if (state.status !== "success") {
			return;
		}

		formRef.current?.reset();
		idempotencyKeyManager.reset();
	}, [idempotencyKeyManager, state]);

	return (
		<CaptureComposerView
			ref={formRef}
			action={formAction}
			pending={pending}
			fieldError={
				state.status === "error" ? state.fieldErrors?.rawText : undefined
			}
			message={state.status === "idle" ? undefined : state.message}
		/>
	);
}
