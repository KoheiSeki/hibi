import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listDigestReportsFromApiMock, redirectMock } = vi.hoisted(() => ({
	listDigestReportsFromApiMock: vi.fn(),
	redirectMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/api/digest", () => ({
	listDigestReportsFromApi: listDigestReportsFromApiMock,
}));
vi.mock("@/features/digest/actions", () => ({
	getLatestDigestReportAction: vi.fn(),
	retryDigestReportAction: vi.fn(),
}));

import { DigestSection } from "@/features/digest/digest-section";

const daily = {
	id: "report-daily",
	kind: "daily",
	periodStart: "2026-11-22",
	timezone: "Asia/Tokyo",
	status: "ready",
	content: {
		items: [
			{
				captureId: "capture-1",
				title: "起こして",
				dueAt: "2026-11-23T00:00:00Z",
			},
			{ captureId: "capture-2", title: "牛乳", dueAt: null },
		],
		overdueCount: 1,
		dueTodayCount: 2,
		doneYesterdayCount: 3,
	},
	contentVersion: "daily-digest-v1",
	errorCode: null,
	generatedAt: "2026-11-21T22:00:00Z",
};

const weekly = {
	id: "report-weekly",
	kind: "weekly",
	periodStart: "2026-11-16",
	timezone: "Asia/Tokyo",
	status: "ready",
	content: {
		stats: { capturedCount: 12, doneCount: 8, openCount: 4, overdueCount: 1 },
		summary: "買い物の記録が多い一週間でした。",
	},
	contentVersion: "weekly-review-v1",
	errorCode: null,
	generatedAt: "2026-11-22T22:00:00Z",
};

type Kind = "daily" | "weekly";

function respondWith(reports: Partial<Record<Kind, unknown>>) {
	listDigestReportsFromApiMock.mockImplementation(
		async ({ kind }: { kind: Kind }) => ({
			ok: true,
			data: reports[kind] ? [reports[kind]] : [],
		}),
	);
}

describe("DigestSection", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("reads the newest report of each kind", async () => {
		// 1 回の一覧では、日ごとの行に押されて、2 週近く前の週次レビューが外れることがある
		respondWith({ daily, weekly });

		await DigestSection();

		expect(listDigestReportsFromApiMock).toHaveBeenCalledTimes(2);
		expect(listDigestReportsFromApiMock).toHaveBeenCalledWith({
			kind: "daily",
			limit: 1,
		});
		expect(listDigestReportsFromApiMock).toHaveBeenCalledWith({
			kind: "weekly",
			limit: 1,
		});
	});

	it("renders the latest daily digest with its items and counts", async () => {
		respondWith({ daily });

		const html = renderToStaticMarkup(await DigestSection());

		expect(html).toContain("朝のダイジェスト");
		expect(html).toContain("起こして");
		expect(html).toContain("09:00");
		expect(html).toContain('href="/captures/capture-1"');
		expect(html).toContain("牛乳");
		expect(html).toContain("期限なし");
		expect(html).toContain("期限が過ぎた 1 件");
		expect(html).toContain("今日が期限 2 件");
		expect(html).toContain("昨日 3 件完了");
		expect(html).not.toContain("週次レビュー");
	});

	it("renders the latest weekly review with its summary and stats", async () => {
		respondWith({ weekly });

		const html = renderToStaticMarkup(await DigestSection());

		expect(html).toContain("週次レビュー");
		expect(html).toContain("買い物の記録が多い一週間でした。");
		expect(html).toContain("記録 12 件");
		expect(html).toContain("完了 8 件");
		expect(html).toContain("未完了 4 件");
		expect(html).toContain("期限超過 1 件");
	});

	it("puts the daily digest before the weekly review", async () => {
		respondWith({ daily, weekly });

		const html = renderToStaticMarkup(await DigestSection());

		expect(html.indexOf("朝のダイジェスト")).toBeGreaterThan(-1);
		expect(html.indexOf("朝のダイジェスト")).toBeLessThan(
			html.indexOf("週次レビュー"),
		);
	});

	it("renders the empty state when there are no reports", async () => {
		respondWith({});

		const html = renderToStaticMarkup(await DigestSection());

		expect(html).toContain("ダイジェストは毎朝 7 時に作ります");
	});

	it("redirects to /login when unauthenticated", async () => {
		listDigestReportsFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(DigestSection()).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});

	it("renders the API error message for other failures", async () => {
		listDigestReportsFromApiMock.mockResolvedValue({
			ok: false,
			error: { kind: "network", message: "fetch failed" },
		});

		const html = renderToStaticMarkup(await DigestSection());

		expect(html).toContain("通信に失敗しました");
		expect(html).not.toContain("ダイジェストは毎朝 7 時に作ります");
	});
});
