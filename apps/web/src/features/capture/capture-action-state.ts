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
export type GetCaptureActionState = ActionState<CaptureResponse>;
export type RetryCaptureActionState = ActionState<CaptureResponse>;
export type AcceptCaptureScenarioActionState = ActionState<CaptureResponse>;
/** 完了にする操作の結果。成功すると、更新後の記録を持つ。 */
export type MarkScenarioDoneActionState = ActionState<CaptureResponse>;
/** 未完了に戻す操作の結果。成功すると、更新後の記録を持つ。 */
export type UnmarkScenarioDoneActionState = ActionState<CaptureResponse>;

export const initialUpdateCaptureActionState: UpdateCaptureActionState = {
	status: "idle",
};
