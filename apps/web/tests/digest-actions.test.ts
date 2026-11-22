import { beforeEach, describe, expect, it, vi } from "vitest";

const {
	listDigestReportsFromApiMock,
	notFoundMock,
	redirectMock,
	retryDigestReportFromApiMock,
	revalidatePathMock,
} = vi.hoisted(() => ({
	listDigestReportsFromApiMock: vi.fn(),
	notFoundMock: vi.fn(),
	redirectMock: vi.fn(),
	retryDigestReportFromApiMock: vi.fn(),
	revalidatePathMock: vi.fn(),
}));

vi.mock("@/lib/api/digest", () => ({
	listDigestReportsFromApi: listDigestReportsFromApiMock,
	retryDigestReportFromApi: retryDigestReportFromApiMock,
}));
vi.mock("next/navigation", () => ({
	notFound: notFoundMock,
	redirect: redirectMock,
}));
vi.mock("next/cache", () => ({ revalidatePath: revalidatePathMock }));

import {
	getLatestDigestReportAction,
	retryDigestReportAction,
} from "@/features/digest/actions";

const pendingReport = {
	id: "report-1",
	kind: "daily",
	periodStart: "2026-11-22",
	timezone: "Asia/Tokyo",
	status: "pending",
	content: null,
	contentVersion: "daily-digest-v1",
	errorCode: null,
	generatedAt: null,
};

const unauthenticated = {
	ok: false,
	error: {
		kind: "unauthenticated",
		message: "Authentication is required.",
	},
};

describe("retryDigestReportAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("revalidates /captures/digest and returns the report", async () => {
		retryDigestReportFromApiMock.mockResolvedValue({
			ok: true,
			data: pendingReport,
		});

		const state = await retryDigestReportAction("report-1");

		expect(retryDigestReportFromApiMock).toHaveBeenCalledWith("report-1");
		expect(revalidatePathMock).toHaveBeenCalledWith("/captures/digest");
		expect(state).toEqual({
			status: "success",
			data: pendingReport,
			message: "もう一度作っています。",
		});
	});

	it("rejects an empty id without calling the API", async () => {
		const state = await retryDigestReportAction("");

		expect(retryDigestReportFromApiMock).not.toHaveBeenCalled();
		expect(state).toEqual({
			status: "error",
			message: "もう一度作れませんでした。",
		});
	});

	it("keeps a missing report as an in-page error", async () => {
		// 画面全体を 404 にせず、カードの下にエラーを出す
		retryDigestReportFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/digest-report-not-found",
					title: "Digest report not found",
					status: 404,
					detail: "The requested digest report does not exist.",
					requestId: "request-404",
				},
			},
		});

		const state = await retryDigestReportAction("report-1");

		expect(notFoundMock).not.toHaveBeenCalled();
		expect(revalidatePathMock).not.toHaveBeenCalled();
		expect(state).toEqual({
			status: "error",
			message:
				"The requested digest report does not exist.（参照 ID: request-404）",
		});
	});

	it("redirects unauthenticated failures to login", async () => {
		retryDigestReportFromApiMock.mockResolvedValue(unauthenticated);
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(retryDigestReportAction("report-1")).rejects.toThrow(
			"NEXT_REDIRECT",
		);
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});
});

describe("getLatestDigestReportAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("reads the newest report of the kind without revalidating", async () => {
		listDigestReportsFromApiMock.mockResolvedValue({
			ok: true,
			data: [pendingReport],
		});

		const state = await getLatestDigestReportAction("daily");

		expect(listDigestReportsFromApiMock).toHaveBeenCalledWith({
			kind: "daily",
			limit: 1,
		});
		expect(revalidatePathMock).not.toHaveBeenCalled();
		expect(state).toEqual({ status: "success", data: pendingReport });
	});

	it("returns null when the kind has no report", async () => {
		listDigestReportsFromApiMock.mockResolvedValue({ ok: true, data: [] });

		const state = await getLatestDigestReportAction("weekly");

		expect(state).toEqual({ status: "success", data: null });
	});

	it("returns an action error when polling fails", async () => {
		listDigestReportsFromApiMock.mockResolvedValue({
			ok: false,
			error: { kind: "network", message: "fetch failed" },
		});

		const state = await getLatestDigestReportAction("daily");

		expect(state).toEqual({
			status: "error",
			message: "ネットワーク接続を確認して、もう一度お試しください。",
		});
	});

	it("redirects unauthenticated failures to login", async () => {
		listDigestReportsFromApiMock.mockResolvedValue(unauthenticated);
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(getLatestDigestReportAction("daily")).rejects.toThrow(
			"NEXT_REDIRECT",
		);
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});
});
