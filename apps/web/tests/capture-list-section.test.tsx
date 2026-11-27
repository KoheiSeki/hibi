import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listCapturesFromApiMock, redirectMock } = vi.hoisted(() => ({
  listCapturesFromApiMock: vi.fn(),
  redirectMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/api/capture", () => ({
  listCapturesFromApi: listCapturesFromApiMock,
}));

import { CaptureListSection } from "@/features/capture/capture-list-section";

describe("CaptureListSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("maps API captures to list items and preserves pagination metadata", async () => {
    listCapturesFromApiMock.mockResolvedValue({
      ok: true,
      data: {
        data: [
          {
            id: "capture-1",
            rawText: "牛乳を買う",
            status: "pending",
            createdAt: "2026-10-02T05:02:00Z",
            updatedAt: "2026-10-02T05:02:00Z",
          },
        ],
        meta: {
          nextCursor: "next-cursor",
          hasNextPage: true,
        },
      },
    });

    const html = renderToStaticMarkup(await CaptureListSection());

    expect(html).toContain("牛乳を買う");
    expect(html).toContain("14:02");
    expect(html).toContain("整えています");
    expect(html).toContain("さらに表示");
  });

  it("renders the empty state when no captures exist", async () => {
    listCapturesFromApiMock.mockResolvedValue({
      ok: true,
      data: {
        data: [],
        meta: {
          nextCursor: null,
          hasNextPage: false,
        },
      },
    });

    const html = renderToStaticMarkup(await CaptureListSection());

    expect(html).toContain("最初の一文を書いてください");
  });

  it("redirects only unauthenticated client failures to login", async () => {
    listCapturesFromApiMock.mockResolvedValue({
      ok: false,
      error: {
        kind: "unauthenticated",
        message: "Authentication is required.",
      },
    });
    redirectMock.mockImplementation(() => {
      throw new Error("NEXT_REDIRECT");
    });

    await expect(CaptureListSection()).rejects.toThrow("NEXT_REDIRECT");
    expect(redirectMock).toHaveBeenCalledWith("/login");
  });
});
