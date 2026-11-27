import { beforeEach, describe, expect, it, vi } from "vitest";

const { createClientMock, redirectMock, signOutMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  redirectMock: vi.fn(),
  signOutMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/auth/server", () => ({ createClient: createClientMock }));

import { signOutAction } from "@/app/account/actions";

describe("signOutAction", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createClientMock.mockResolvedValue({
      auth: { signOut: signOutMock },
    });
  });

  it("signs out the current session and redirects to login", async () => {
    signOutMock.mockResolvedValue({ error: null });
    redirectMock.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });

    await expect(signOutAction()).rejects.toThrow("NEXT_REDIRECT");
    expect(signOutMock).toHaveBeenCalledWith({ scope: "local" });
    expect(redirectMock).toHaveBeenCalledWith("/login");
  });

  it("does not redirect when Supabase sign out fails", async () => {
    const error = new Error("sign out failed");
    signOutMock.mockResolvedValue({ error });

    await expect(signOutAction()).rejects.toThrow("sign out failed");
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
