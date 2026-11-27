import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { searchCapturesFromApiMock, redirectMock } = vi.hoisted(() => ({
	searchCapturesFromApiMock: vi.fn(),
	redirectMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/api/capture", () => ({
	searchCapturesFromApi: searchCapturesFromApiMock,
}));

import { CaptureSearchResultsSection } from "@/features/capture/capture-search-results-section";

describe("CaptureSearchResultsSection", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders hits with the same rows as the list and no pager", async () => {
		searchCapturesFromApiMock.mockResolvedValue({
			ok: true,
			data: [
				{
					id: "capture-1",
					rawText: "牛乳を買う",
					status: "completed",
					createdAt: "2026-10-02T05:02:00Z",
					updatedAt: "2026-10-02T05:02:00Z",
				},
			],
		});

		const html = renderToStaticMarkup(
			await CaptureSearchResultsSection({ q: "牛乳", mode: "keyword" }),
		);

		expect(searchCapturesFromApiMock).toHaveBeenCalledWith({
			q: "牛乳",
			mode: "keyword",
		});
		expect(html).toContain("牛乳を買う");
		expect(html).toContain("14:02");
		expect(html).toContain('href="/captures/capture-1"');
		expect(html).toContain('aria-label="記録の一覧"');
		expect(html).not.toContain("さらに表示");
	});

	it("renders 見つかりませんでした for an empty result", async () => {
		searchCapturesFromApiMock.mockResolvedValue({ ok: true, data: [] });

		const html = renderToStaticMarkup(
			await CaptureSearchResultsSection({ q: "ミルク", mode: "keyword" }),
		);

		expect(html).toContain("見つかりませんでした");
		expect(html).not.toContain('aria-label="記録の一覧"');
	});

	it("redirects to /login when unauthenticated", async () => {
		searchCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(
			CaptureSearchResultsSection({ q: "牛乳", mode: "keyword" }),
		).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});

	it("renders the API error message for other failures", async () => {
		searchCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: { kind: "network", message: "fetch failed" },
		});

		const html = renderToStaticMarkup(
			await CaptureSearchResultsSection({ q: "ミルク", mode: "semantic" }),
		);

		expect(html).toContain("通信に失敗しました");
		expect(html).not.toContain("見つかりませんでした");
	});
});
