"use server";

import {
	acceptCaptureScenarioFromApi,
	createCaptureFromApi,
	deleteCaptureFromApi,
	getCaptureFromApi,
	listCapturesFromApi,
	markCaptureScenarioDoneFromApi,
	retryCaptureFromApi,
	unmarkCaptureScenarioDoneFromApi,
	updateCaptureFromApi,
} from "@/lib/api/capture";
import type {
	AcceptCaptureScenarioActionState,
	CaptureFieldErrors,
	CreateCaptureActionState,
	DeleteCaptureActionState,
	GetCaptureActionState,
	ListCapturesActionState,
	MarkScenarioDoneActionState,
	RetryCaptureActionState,
	UnmarkScenarioDoneActionState,
	UpdateCaptureActionState,
} from "./capture-action-state";
import { revalidatePath } from "next/cache";
import { notFound, redirect } from "next/navigation";
import { toActionErrorState } from "@/lib/api/action-error";
import { ApiClientErrorPresentation } from "@/lib/api/client-error-message";

export async function createCaptureAction(
	_prev: CreateCaptureActionState,
	formData: FormData,
): Promise<CreateCaptureActionState> {
	const rawText = formData.get("rawText");
	const idempotencyKey = formData.get("idempotencyKey");

	if (typeof rawText !== "string") {
		return {
			status: "error",
			fieldErrors: {
				rawText: "入力内容を確認してください。",
			},
			message: "記録できませんでした。",
		};
	}

	if (typeof idempotencyKey !== "string") {
		return {
			status: "error",
			message: "リクエストを処理できませんでした。",
		};
	}

	const result = await createCaptureFromApi(rawText, idempotencyKey);
	if (!result.ok) {
		return toActionErrorState(result.error, mapCaptureFieldErrors);
	}
	revalidatePath("/captures");

	return {
		status: "success",
		data: result.data,
		message: "記録しました。",
	};
}

export async function listCapturesAction(
	cursor: string,
): Promise<ListCapturesActionState> {
	if (typeof cursor != "string" || cursor.length === 0) {
		return {
			status: "error",
			message: "カーソルが不正です。",
		};
	}

	const result = await listCapturesFromApi({ cursor });
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	return {
		status: "success",
		data: result.data,
	};
}

export async function getCaptureAction(
	captureId: string,
): Promise<GetCaptureActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "記録を取得できませんでした。",
		};
	}

	const result = await getCaptureFromApi(captureId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	return {
		status: "success",
		data: result.data,
	};
}

export async function retryCaptureAction(
	captureId: string,
): Promise<RetryCaptureActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "やり直しを開始できませんでした。",
		};
	}

	const result = await retryCaptureFromApi(captureId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	revalidatePath("/captures");
	revalidatePath(`/captures/${captureId}`);
	return {
		status: "success",
		data: result.data,
		message: "もう一度整えています。",
	};
}

export async function acceptCaptureScenarioAction(
	captureId: string,
): Promise<AcceptCaptureScenarioActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "追加できませんでした。",
		};
	}

	const result = await acceptCaptureScenarioFromApi(captureId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}

	revalidatePath("/captures");
	revalidatePath(`/captures/${captureId}`);
	return {
		status: "success",
		data: result.data,
	};
}

export async function updateCaptureAction(
	captureId: string,
	_prev: UpdateCaptureActionState,
	formData: FormData,
): Promise<UpdateCaptureActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "更新対象が不正です。",
		};
	}
	const rawText = formData.get("rawText");

	if (typeof rawText !== "string") {
		return {
			status: "error",
			fieldErrors: {
				rawText: "入力内容を確認してください。",
			},
			message: "更新に失敗しました。",
		};
	}

	const result = await updateCaptureFromApi(captureId, rawText);
	if (!result.ok) {
		if (
			result.error.kind === "problem" &&
			result.error.problem.status === 404
		) {
			notFound();
		}

		return toActionErrorState(result.error, mapCaptureFieldErrors);
	}
	revalidatePath("/captures");
	revalidatePath(`/captures/${captureId}`);

	return {
		status: "success",
		data: result.data,
		message: "更新しました。",
	};
}

/**
 * 記録のシナリオを完了にし、今日やることの一覧と詳細を更新する。
 *
 * 一覧の 1 行が消えても画面全体は 404 にせず、失敗は行の近くに出すエラーとして返す。
 * 未認証のときはログインへ移る。
 *
 * @param captureId - 完了にする記録の id。空だとAPIを呼ばずにエラーを返す。
 * @returns 成功したときは更新後の記録。失敗したときは画面に出すメッセージ。
 */
export async function markScenarioDoneAction(
	captureId: string,
): Promise<MarkScenarioDoneActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "完了にできませんでした。",
		};
	}

	const result = await markCaptureScenarioDoneFromApi(captureId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}
	revalidatePath("/captures/today");
	revalidatePath(`/captures/${captureId}`);
	return {
		status: "success",
		data: result.data,
	};
}

export async function deleteCaptureAction(
	captureId: string,
): Promise<DeleteCaptureActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "削除に失敗しました。",
		};
	}

	const result = await deleteCaptureFromApi(captureId);
	if (!result.ok) {
		if (
			result.error.kind === "problem" &&
			result.error.problem.status === 404
		) {
			notFound();
		}

		return toActionErrorState(result.error);
	}
	revalidatePath("/captures");
	redirect("/captures");
}

/**
 * 記録のシナリオを未完了に戻し、今日やることの一覧と詳細を更新する。
 *
 * @param captureId - 未完了に戻す記録の id。空だとAPIを呼ばずにエラーを返す。
 * @returns 成功したときは更新後の記録。失敗したときは画面に出すメッセージ。
 */
export async function unmarkScenarioDoneAction(
	captureId: string,
): Promise<UnmarkScenarioDoneActionState> {
	if (typeof captureId !== "string" || captureId.length === 0) {
		return {
			status: "error",
			message: "未完了に戻せませんでした。",
		};
	}

	const result = await unmarkCaptureScenarioDoneFromApi(captureId);
	if (!result.ok) {
		return toActionErrorState(result.error);
	}
	revalidatePath("/captures/today");
	revalidatePath(`/captures/${captureId}`);
	return {
		status: "success",
		data: result.data,
	};
}

function mapCaptureFieldErrors(
	presentation: ApiClientErrorPresentation,
): CaptureFieldErrors | undefined {
	const rawText = presentation.fieldErrors?.find(
		({ pointer }) => pointer === "/rawText",
	)?.detail;
	return rawText ? { rawText } : undefined;
}
