import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { listTodayCapturesFromApiMock, redirectMock } = vi.hoisted(() => ({
	listTodayCapturesFromApiMock: vi.fn(),
	redirectMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/api/capture", () => ({
	listTodayCapturesFromApi: listTodayCapturesFromApiMock,
}));
vi.mock("@/features/capture/actions", () => ({
	markScenarioDoneAction: vi.fn(),
}));

import { TodaySection } from "@/features/capture/today-section";

const reminder = {
	id: "capture-1",
	rawText: "明日の 9 時に起こして",
	status: "completed",
	createdAt: "2026-11-10T05:00:00Z",
	updatedAt: "2026-11-10T05:00:00Z",
	scenario: {
		route: "reminder",
		status: "proposed",
		title: "起こして",
		remindText: "明日の 9 時",
		policyVersion: "capture-scenario-v1",
		dueAt: "2026-11-11T00:00:00Z",
		doneAt: null,
	},
};

const shopping = {
	id: "capture-2",
	rawText: "牛乳を買う",
	status: "completed",
	createdAt: "2026-11-10T05:01:00Z",
	updatedAt: "2026-11-10T05:01:00Z",
	scenario: {
		route: "shopping",
		status: "proposed",
		title: "牛乳",
		policyVersion: "capture-scenario-v1",
		dueAt: null,
		doneAt: null,
	},
};

describe("TodaySection", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders the scenario title, the due time and a link to the detail", async () => {
		listTodayCapturesFromApiMock.mockResolvedValue({
			ok: true,
			data: [reminder],
		});

		const html = renderToStaticMarkup(await TodaySection());

		expect(html).toContain("起こして");
		expect(html).toContain("09:00");
		expect(html).toContain('href="/captures/capture-1"');
		expect(html).toContain("完了にする");
	});

	it("keeps the order of the API and omits the time without a deadline", async () => {
		listTodayCapturesFromApiMock.mockResolvedValue({
			ok: true,
			data: [shopping, reminder],
		});

		const html = renderToStaticMarkup(await TodaySection());

		expect(html.indexOf("牛乳")).toBeGreaterThan(-1);
		expect(html.indexOf("牛乳")).toBeLessThan(html.indexOf("起こして"));
		// 期限のある行にだけ時刻が出る
		expect(html.match(/<time/g)).toHaveLength(1);
	});

	it("renders the empty state when there is nothing to do today", async () => {
		listTodayCapturesFromApiMock.mockResolvedValue({ ok: true, data: [] });

		const html = renderToStaticMarkup(await TodaySection());

		expect(html).toContain("今日やることはありません");
		expect(html).not.toContain("完了にする");
	});

	it("redirects to /login when unauthenticated", async () => {
		listTodayCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(TodaySection()).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});

	it("renders the API error message for other failures", async () => {
		listTodayCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: { kind: "network", message: "fetch failed" },
		});

		const html = renderToStaticMarkup(await TodaySection());

		expect(html).toContain("通信に失敗しました");
		expect(html).not.toContain("今日やることはありません");
	});
});
