import { describe, expect, it } from "vitest";
import { presentApiClientError } from "@/lib/api/client-error-message";
import { normalizeGeneratedResult } from "@/lib/api/request-api";

const unauthorizedProblem = {
  type: "https://api.hibi.example/problems/unauthorized",
  title: "Unauthorized",
  status: 401,
  detail: "Authentication is required.",
  requestId: "req-unauthorized-1",
} as const;

describe("auth failure contract (Web consumer)", () => {
  it("maps API 401 Problem Details separately from client-side unauthenticated", () => {
    const fromApi = presentApiClientError({
      kind: "problem",
      problem: unauthorizedProblem,
    });
    const fromClient = presentApiClientError({
      kind: "unauthenticated",
      message: "Authentication is required.",
    });

    expect(fromApi.title).toBe("認証に失敗しました");
    expect(fromClient.title).toBe("ログインが必要です");
    expect(fromApi.requestId).toBe("req-unauthorized-1");
    expect(fromClient.requestId).toBeUndefined();
  });

  it("normalizes generated client 401 problems as kind problem, not unauthenticated", () => {
    expect(
      normalizeGeneratedResult({
        data: undefined,
        error: unauthorizedProblem,
        response: new Response(JSON.stringify(unauthorizedProblem), {
          status: 401,
          headers: { "content-type": "application/problem+json" },
        }),
      }),
    ).toEqual({
      ok: false,
      error: { kind: "problem", problem: unauthorizedProblem },
    });
  });

  it("does not treat 500 internal errors as authentication failures", () => {
    const internalError = {
      type: "https://api.hibi.example/problems/internal-error",
      title: "Internal server error",
      status: 500,
      detail: "An unexpected error occurred.",
      requestId: "req-internal-1",
    };

    expect(
      presentApiClientError({ kind: "problem", problem: internalError }),
    ).toMatchObject({
      title: "サーバーで問題が発生しました",
      requestId: "req-internal-1",
    });
    expect(
      presentApiClientError({ kind: "problem", problem: internalError }).detail,
    ).not.toBe("An unexpected error occurred.");
    expect(
      presentApiClientError({ kind: "problem", problem: internalError }).title,
    ).not.toBe("認証に失敗しました");
  });
});
