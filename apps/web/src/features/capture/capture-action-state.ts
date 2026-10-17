import type {
	ApiResponseWithMetaListCaptureResponseCursorMeta,
	CaptureResponse,
} from "@hibi/api-client";
import type { ActionState } from "@/lib/action-state";
export type CaptureFieldErrors = {
	rawText?: string;
};
export type CreateCaptureActionState = ActionState<
	CaptureResponse,
	CaptureFieldErrors
>;

export type ListCapturesActionState =
	ActionState<ApiResponseWithMetaListCaptureResponseCursorMeta>;

export const initialCreateCaptureActionState: CreateCaptureActionState = {
	status: "idle",
};

export type UpdateCaptureActionState = ActionState<
	CaptureResponse,
	CaptureFieldErrors
>;
export type DeleteCaptureActionState = ActionState<void>;

export const initialUpdateCaptureActionState: UpdateCaptureActionState = {
	status: "idle",
};
