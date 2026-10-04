"use server";

import { createCaptureFromApi } from "@/lib/api/capture";
import type { CreateCaptureActionState } from "./capture-action-state";
import { redirect } from "next/navigation";
import { presentApiClientError } from "@/lib/api/client-error-message";
import { revalidatePath } from "next/cache";

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
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		const presentation = presentApiClientError(result.error);
		const rawTextError = presentation.fieldErrors?.find(
			({ pointer }) => pointer === "/rawText",
		)?.detail;

		return {
			status: "error",
			message: presentation.requestId
				? `${presentation.detail}（参照 ID: ${presentation.requestId}）`
				: presentation.detail,
			...(rawTextError
				? {
						fieldErrors: {
							rawText: rawTextError,
						},
					}
				: {}),
		};
	}
	revalidatePath("/captures");

	return {
		status: "success",
		data: result.data,
		message: "記録しました。",
	};
}
