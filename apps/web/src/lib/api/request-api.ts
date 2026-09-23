export type FieldProblem = { pointer: string; code: string; detail: string };
export type ApiProblem = {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  requestId: string;
  errors?: FieldProblem[];
};
export type ApiClientError =
  | { kind: "problem"; problem: ApiProblem }
  | { kind: "network"; message: string }
  | { kind: "aborted" }
  | { kind: "invalid-response"; message: string };
export type ApiResult<T> =
  { ok: true; data: T } | { ok: false; error: ApiClientError };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isProblem(value: unknown): value is ApiProblem {
  return (
    isRecord(value) &&
    typeof value.type === "string" &&
    typeof value.title === "string" &&
    typeof value.status === "number" &&
    typeof value.detail === "string" &&
    typeof value.requestId === "string"
  );
}

export async function requestApi<T>(
  path: string,
  init?: RequestInit,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      return { ok: false, error: { kind: "aborted" } };
    return {
      ok: false,
      error: {
        kind: "network",
        message:
          error instanceof Error ? error.message : "Network request failed.",
      },
    };
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      return { ok: false, error: { kind: "aborted" } };
    return {
      ok: false,
      error: {
        kind: "invalid-response",
        message: "Response body was not valid JSON.",
      },
    };
  }

  if (!response.ok) {
    return isProblem(body)
      ? { ok: false, error: { kind: "problem", problem: body } }
      : {
          ok: false,
          error: {
            kind: "invalid-response",
            message: "Error response was not RFC 9457 Problem Details.",
          },
        };
  }
  if (!isRecord(body) || !("data" in body))
    return {
      ok: false,
      error: {
        kind: "invalid-response",
        message: "Success response did not contain data.",
      },
    };
  return { ok: true, data: body.data as T };
}
