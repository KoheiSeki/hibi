import { describe, expect, it } from "vitest";
import {
  presentApiClientError,
  shouldOfferReLogin,
} from "@/lib/api/client-error-message";

describe("presentApiClientError", () => {
  it("offers re-login only for API 401 problems", () => {
    expect(
      shouldOfferReLogin({
        kind: "problem",
        problem: {
          type: "https://api.hibi.example/problems/unauthorized",
          title: "Unauthorized",
          status: 401,
          detail: "Authentication is required.",
          requestId: "req-1",
        },
      }),
    ).toBe(true);

    expect(
      shouldOfferReLogin({
        kind: "unauthenticated",
        message: "Authentication is required.",
      }),
    ).toBe(false);

    expect(
      shouldOfferReLogin({
        kind: "problem",
        problem: {
          type: "https://api.hibi.example/problems/internal-error",
          title: "Internal server error",
          status: 500,
          detail: "An unexpected error occurred.",
          requestId: "req-500",
        },
      }),
    ).toBe(false);
  });

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

  it("maps 500 problems with user-safe Japanese copy", () => {
    expect(
      presentApiClientError({
        kind: "problem",
        problem: {
          type: "https://api.hibi.example/problems/internal-error",
          title: "Internal server error",
          status: 500,
          detail: "An unexpected error occurred.",
          requestId: "req-500",
        },
      }),
    ).toEqual({
      title: "サーバーで問題が発生しました",
      detail:
        "処理を完了できませんでした。時間をおいて再度お試しください。改善しない場合は、参照 ID を添えてお問い合わせください。",
      requestId: "req-500",
      fieldErrors: undefined,
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
