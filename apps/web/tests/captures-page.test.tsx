import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { createClientMock, redirectMock } = vi.hoisted(() => ({
  createClientMock: vi.fn(),
  redirectMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/auth/server", () => ({ createClient: createClientMock }));
vi.mock("@/lib/date-time", () => ({
  formatJstDateLabel: () => "10月4日 日",
}));
vi.mock("@/features/capture/capture-list-section", () => ({
  CaptureListSection: () => <div>timeline</div>,
}));

import CapturePage from "@/app/captures/page";

describe("CapturePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createClientMock.mockResolvedValue({
      auth: {
        getUser: vi.fn().mockResolvedValue({
          data: { user: { id: "user-1" } },
        }),
      },
    });
  });

  it("composes the date, composer, and capture list for an authenticated user", async () => {
    const html = renderToStaticMarkup(await CapturePage());

    expect(html).toContain("10月4日 日");
    expect(html).toContain("何を残しますか");
    expect(html).toContain("timeline");
  });

  it("redirects an unauthenticated user to login", async () => {
    createClientMock.mockResolvedValue({
      auth: {
        getUser: vi.fn().mockResolvedValue({ data: { user: null } }),
      },
    });
    redirectMock.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });

    await expect(CapturePage()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirectMock).toHaveBeenCalledWith("/login");
  });
});
