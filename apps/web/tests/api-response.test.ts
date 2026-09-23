import { describe, expect, it, vi } from "vitest";
import { requestApi } from "@/lib/api/request-api";

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
});
