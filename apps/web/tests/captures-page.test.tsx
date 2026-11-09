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
vi.mock("@/features/capture/capture-search-results-section", () => ({
	CaptureSearchResultsSection: ({ q, mode }: { q: string; mode: string }) => (
		<div>
			results:{q}:{mode}
		</div>
	),
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
		const html = renderToStaticMarkup(
			await CapturePage({ searchParams: Promise.resolve({}) }),
		);

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

		await expect(
			CapturePage({ searchParams: Promise.resolve({}) }),
		).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});

	it("renders the search form and the timeline when there is no search", async () => {
		const html = renderToStaticMarkup(
			await CapturePage({ searchParams: Promise.resolve({}) }),
		);

		expect(html).toContain('role="search"');
		expect(html).toContain("timeline");
		expect(html).not.toContain("results:");
	});

	it("renders the results instead of the timeline when q is given", async () => {
		const html = renderToStaticMarkup(
			await CapturePage({
				searchParams: Promise.resolve({ q: "牛乳", mode: "semantic" }),
			}),
		);

		expect(html).toContain("results:牛乳:semantic");
		expect(html).toContain('value="牛乳"');
		expect(html).not.toContain("timeline");
	});

	it("falls back to the timeline when q is blank", async () => {
		const html = renderToStaticMarkup(
			await CapturePage({ searchParams: Promise.resolve({ q: "  " }) }),
		);

		expect(html).toContain("timeline");
		expect(html).not.toContain("results:");
	});
});
