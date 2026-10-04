import type {
	ApiResponseWithMetaListCaptureResponseCursorMeta,
	CaptureResponse,
} from "@hibi/api-client";
import type { ActionState } from "@/lib/action-state";
type CaptureFieldErrors = {
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
