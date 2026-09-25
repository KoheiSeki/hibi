import { describe, expect, it } from "vitest";
import { presentApiClientError } from "@/lib/api/client-error-message";

describe("presentApiClientError", () => {
  it("maps network errors", () => {
    expect(
      presentApiClientError({ kind: "network", message: "fetch failed" }),
    ).toMatchObject({
      title: "通信に失敗しました",
    });
  });

  it("maps timeout errors", () => {
    expect(
      presentApiClientError({
        kind: "timeout",
        message: "The request timed out.",
      }),
    ).toMatchObject({
      title: "応答がありませんでした",
      detail: "The request timed out.",
    });
  });

  it("maps RFC 9457 problem details", () => {
    expect(
      presentApiClientError({
        kind: "problem",
        problem: {
          type: "https://api.hibi.example/problems/unauthorized",
          title: "Unauthorized",
          status: 401,
          detail: "Authentication failed.",
          requestId: "req-1",
        },
      }),
    ).toEqual({
      title: "認証に失敗しました",
      detail: "Authentication failed.",
      requestId: "req-1",
      fieldErrors: undefined,
    });
  });
});
