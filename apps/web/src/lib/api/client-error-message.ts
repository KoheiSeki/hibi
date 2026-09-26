import type { ApiClientError, ApiProblem } from "./request-api";

export type ApiClientErrorPresentation = {
	title: string;
	detail: string;
	requestId?: string;
	fieldErrors?: { pointer: string; detail: string }[];
};

/** 401 Problem のみ再ログイン導線を出す（500 等と区別）。 */
export function shouldOfferReLogin(error: ApiClientError): boolean {
	return error.kind === "problem" && error.problem.status === 401;
}

export function presentApiClientError(
	error: ApiClientError,
): ApiClientErrorPresentation {
	switch (error.kind) {
		case "unauthenticated":
			return {
				title: "ログインが必要です",
				detail: error.message,
			};
		case "problem":
			return presentProblem(error.problem);
		case "network":
			return {
				title: "通信に失敗しました",
				detail: "ネットワーク接続を確認して、もう一度お試しください。",
			};
		case "timeout":
			return {
				title: "応答がありませんでした",
				detail: error.message,
			};
		case "aborted":
			return {
				title: "処理を中断しました",
				detail: "操作はキャンセルされました。",
			};
		case "invalid-response":
			return {
				title: "サーバーから不正な応答がありました",
				detail: error.message,
			};
	}
}

function presentProblem(problem: ApiProblem): ApiClientErrorPresentation {
	if (problem.status === 401) {
		return {
			title: "認証に失敗しました",
			detail: problem.detail,
			requestId: problem.requestId,
			fieldErrors: mapFieldErrors(problem),
		};
	}

	if (problem.status === 403) {
		return {
			title: "アクセスが拒否されました",
			detail: problem.detail,
			requestId: problem.requestId,
			fieldErrors: mapFieldErrors(problem),
		};
	}

	if (problem.status === 404) {
		return {
			title: "リソースが見つかりません",
			detail: problem.detail,
			requestId: problem.requestId,
			fieldErrors: mapFieldErrors(problem),
		};
	}

	if (problem.status === 500) {
		return {
			title: "サーバーで問題が発生しました",
			detail:
				"処理を完了できませんでした。時間をおいて再度お試しください。改善しない場合は、参照 ID を添えてお問い合わせください。",
			requestId: problem.requestId,
			fieldErrors: mapFieldErrors(problem),
		};
	}

	if (problem.status === 503) {
		return {
			title: "サービスを一時的に利用できません",
			detail:
				"認証サービスなどが一時的に利用できません。しばらく待ってからもう一度お試しください。",
			requestId: problem.requestId,
			fieldErrors: mapFieldErrors(problem),
		};
	}

	return {
		title: problem.title,
		detail: problem.detail,
		requestId: problem.requestId,
		fieldErrors: mapFieldErrors(problem),
	};
}

function mapFieldErrors(problem: ApiProblem) {
	return problem.errors?.map(({ pointer, detail }) => ({
		pointer,
		detail,
	}));
}
