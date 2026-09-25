import type { ApiClientError, ApiProblem } from "./request-api";

export type ApiClientErrorPresentation = {
  title: string;
  detail: string;
  requestId?: string;
  fieldErrors?: { pointer: string; detail: string }[];
};

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
  const title =
    problem.status === 401
      ? "認証に失敗しました"
      : problem.status === 403
        ? "アクセスが拒否されました"
        : problem.status === 404
          ? "リソースが見つかりません"
          : problem.title;

  return {
    title,
    detail: problem.detail,
    requestId: problem.requestId,
    fieldErrors: problem.errors?.map(({ pointer, detail }) => ({
      pointer,
      detail,
    })),
  };
}
