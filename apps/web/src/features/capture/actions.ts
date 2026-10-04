"use server";

import { createCaptureFromApi, listCapturesFromApi } from "@/lib/api/capture";
import type {
	CreateCaptureActionState,
	ListCapturesActionState,
} from "./capture-action-state";
import { revalidatePath } from "next/cache";
import { createActionError } from "@/lib/api/action-error";

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
		return createActionError(result.error, (presentation) => {
			const rawText = presentation.fieldErrors?.find(
				({ pointer }) => pointer === "/rawText",
			)?.detail;
			return rawText ? { rawText } : undefined;
		});
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
		return createActionError(result.error);
	}

	return {
		status: "success",
		data: result.data,
	};
}
