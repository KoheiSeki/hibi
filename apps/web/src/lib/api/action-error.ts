import { redirect } from "next/navigation";
import {
	ApiClientErrorPresentation,
	presentApiClientError,
} from "./client-error-message";
import { ApiClientError } from "./request-api";

type ActionError<TFieldErrors> = {
	status: "error";
	message: string;
	fieldErrors?: TFieldErrors;
};

export function toActionErrorState<TFieldErrors = never>(
	error: ApiClientError,
	mapFieldErrors?: (
		presentation: ApiClientErrorPresentation,
	) => TFieldErrors | undefined,
): ActionError<TFieldErrors> {
	if (error.kind === "unauthenticated") {
		redirect("/login");
	}
	const presentation = presentApiClientError(error);
	const fieldErrors = mapFieldErrors?.(presentation);
	return {
		status: "error",
		message: presentation.requestId
			? `${presentation.detail}（参照 ID: ${presentation.requestId}）`
			: presentation.detail,
		...(fieldErrors ? { fieldErrors } : {}),
	};
}
