"use server";

import {
	createCaptureFromApi,
	deleteCaptureFromApi,
	listCapturesFromApi,
	updateCaptureFromApi,
} from "@/lib/api/capture";
import type {
	CaptureFieldErrors,
	CreateCaptureActionState,
	DeleteCaptureActionState,
	ListCapturesActionState,
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

function mapCaptureFieldErrors(
	presentation: ApiClientErrorPresentation,
): CaptureFieldErrors | undefined {
	const rawText = presentation.fieldErrors?.find(
		({ pointer }) => pointer === "/rawText",
	)?.detail;
	return rawText ? { rawText } : undefined;
}
