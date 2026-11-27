import { describe, expect, it, vi } from "vitest";
import {
  normalizeGeneratedEmptyResult,
  normalizeGeneratedResult,
  requestApi,
} from "@/lib/api/request-api";

describe("requestApi", () => {
  it("unwraps a successful data response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ data: { status: "ok" } }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    await expect(requestApi<{ status: string }>("/health")).resolves.toEqual({
      ok: true,
      data: { status: "ok" },
    });
  });

  it("normalizes RFC 9457 errors", async () => {
    const problem = {
      type: "https://api.hibi.example/problems/unauthorized",
      title: "Unauthorized",
      status: 401,
      detail: "Authentication required.",
      requestId: "req-1",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify(problem), {
            status: 401,
            headers: { "content-type": "application/problem+json" },
          }),
      ),
    );
    await expect(requestApi("/protected")).resolves.toEqual({
      ok: false,
      error: { kind: "problem", problem },
    });
  });

  it("classifies malformed success payloads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ status: "ok" }), {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
    const result = await requestApi("/health");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe("invalid-response");
  });

  it("classifies malformed JSON as an invalid response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("{not-json", {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );

    const result = await requestApi("/health");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe("invalid-response");
  });

  it("classifies fetch failures as network errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed");
      }),
    );

    const result = await requestApi("/health");

    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.kind).toBe("network");
  });

  it("classifies fetch timeouts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new DOMException("The operation timed out.", "TimeoutError");
      }),
    );

    const result = await requestApi("/health");

    expect(result).toEqual({
      ok: false,
      error: { kind: "timeout", message: "The request timed out." },
    });
  });

  it("classifies aborted fetch requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new DOMException("The operation was aborted.", "AbortError");
      }),
    );

    const result = await requestApi("/health");

    expect(result).toEqual({ ok: false, error: { kind: "aborted" } });
  });

  it("classifies aborted response body reads", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          ({
            ok: true,
            json: async () => {
              throw new DOMException("The operation was aborted.", "AbortError");
            },
          }) as unknown as Response,
      ),
    );

    const result = await requestApi("/health");

    expect(result).toEqual({ ok: false, error: { kind: "aborted" } });
  });
});

describe("normalizeGeneratedResult", () => {
  it("unwraps successful generated payloads", () => {
    expect(
      normalizeGeneratedResult({ data: { data: { userId: "u-1" } } }),
    ).toEqual({ ok: true, data: { userId: "u-1" } });
  });

  it("classifies generated client timeouts without a response", () => {
    expect(
      normalizeGeneratedResult({
        data: undefined,
        error: new DOMException("The operation timed out.", "TimeoutError"),
      }),
    ).toEqual({
      ok: false,
      error: { kind: "timeout", message: "The request timed out." },
    });
  });

  it("classifies generated client aborts without a response", () => {
    expect(
      normalizeGeneratedResult({
        data: undefined,
        error: new DOMException("The operation was aborted.", "AbortError"),
      }),
    ).toEqual({ ok: false, error: { kind: "aborted" } });
  });
});

describe("normalizeGeneratedEmptyResult", () => {
  it("treats an empty successful response as success", () => {
    expect(
      normalizeGeneratedEmptyResult({
        data: undefined,
        error: undefined,
        response: new Response(null, { status: 204 }),
      }),
    ).toEqual({ ok: true, data: undefined });
  });

  it("preserves a problem response", () => {
    const problem = {
      type: "https://api.hibi.example/problems/not-found",
      title: "Not found",
      status: 404,
      detail: "Capture was not found.",
      requestId: "request-404",
    };

    expect(
      normalizeGeneratedEmptyResult({
        data: undefined,
        error: problem,
        response: new Response(null, { status: 404 }),
      }),
    ).toEqual({ ok: false, error: { kind: "problem", problem } });
  });

  it("classifies a missing response as a network error", () => {
    expect(
      normalizeGeneratedEmptyResult({
        data: undefined,
        error: new TypeError("fetch failed"),
      }),
    ).toEqual({
      ok: false,
      error: { kind: "network", message: "fetch failed" },
    });
  });
});
