import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

const { createClientMock, getCurrentUserMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  getCurrentUserMock: vi.fn(),
}));

vi.mock("@/lib/auth/server", () => ({
  createClient: createClientMock,
}));

vi.mock("@hibi/api-client", () => ({
  getCurrentUser: getCurrentUserMock,
}));

import { getCurrentUserFromApi } from "@/lib/api/server";

function mockSession(accessToken: string | undefined) {
  createClientMock.mockResolvedValue({
    auth: {
      getSession: async () => ({
        data: {
          session: accessToken ? { access_token: accessToken } : null,
        },
      }),
    },
  });
}

describe("getCurrentUserFromApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    process.env.HIBI_API_BASE_URL = "http://127.0.0.1:8000";
  });

  afterEach(() => {
    delete process.env.HIBI_API_BASE_URL;
  });

  it("returns unauthenticated when there is no access token", async () => {
    mockSession(undefined);

    await expect(getCurrentUserFromApi()).resolves.toEqual({
      ok: false,
      error: {
        kind: "unauthenticated",
        message: "Authentication is required.",
      },
    });
    expect(getCurrentUserMock).not.toHaveBeenCalled();
  });

  it("calls getCurrentUser with server base URL and bearer token", async () => {
    mockSession("access-token-123");
    getCurrentUserMock.mockResolvedValue({
      data: { data: { userId: "11111111-1111-4111-8111-111111111111" } },
    });

    await expect(getCurrentUserFromApi()).resolves.toEqual({
      ok: true,
      data: { userId: "11111111-1111-4111-8111-111111111111" },
    });
    expect(getCurrentUserMock).toHaveBeenCalledWith({
      baseUrl: "http://127.0.0.1:8000",
      auth: "access-token-123",
    });
  });

  it("throws when HIBI_API_BASE_URL is not configured", async () => {
    delete process.env.HIBI_API_BASE_URL;
    mockSession("access-token-123");

    await expect(getCurrentUserFromApi()).rejects.toThrow(
      "HIBI_API_BASE_URL is not configured.",
    );
    expect(getCurrentUserMock).not.toHaveBeenCalled();
  });

  it("maps RFC 9457 problem details from the generated client", async () => {
    mockSession("access-token-123");
    const problem = {
      type: "https://api.hibi.example/problems/unauthorized",
      title: "Unauthorized",
      status: 401,
      detail: "Authentication failed.",
      requestId: "req-auth-1",
    };
    getCurrentUserMock.mockResolvedValue({
      data: undefined,
      error: problem,
      response: new Response(JSON.stringify(problem), { status: 401 }),
    });

    await expect(getCurrentUserFromApi()).resolves.toEqual({
      ok: false,
      error: { kind: "problem", problem },
    });
  });
});
