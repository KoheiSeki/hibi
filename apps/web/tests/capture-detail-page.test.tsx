import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getCaptureFromApiMock, notFoundMock, requireUserMock } =
	vi.hoisted(() => ({
		getCaptureFromApiMock: vi.fn(),
		notFoundMock: vi.fn(),
		requireUserMock: vi.fn(),
	}));

vi.mock("@/lib/api/capture", () => ({
	getCaptureFromApi: getCaptureFromApiMock,
}));
vi.mock("@/lib/auth/require-user", () => ({
	requireUser: requireUserMock,
}));
vi.mock("next/navigation", () => ({
	notFound: notFoundMock,
	redirect: vi.fn(),
}));

import CaptureDetailPage from "@/app/captures/[captureId]/page";
import CaptureNotFound from "@/app/captures/[captureId]/not-found";

describe("CaptureDetailPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("renders the fetched capture in the detail editor", async () => {
		getCaptureFromApiMock.mockResolvedValue({
			ok: true,
			data: {
				id: "capture-1",
				rawText: "牛乳を買う",
				status: "active",
				createdAt: "2026-10-04T09:30:00Z",
				updatedAt: "2026-10-04T09:30:00Z",
			},
		});

		const html = renderToStaticMarkup(
			await CaptureDetailPage({
				params: Promise.resolve({ captureId: "capture-1" }),
			}),
		);

		expect(requireUserMock).toHaveBeenCalledOnce();
		expect(getCaptureFromApiMock).toHaveBeenCalledWith("capture-1");
		expect(html).toContain("10月4日 18:30");
		expect(html).toContain("牛乳を買う");
		expect(html).toContain("保存する");
		expect(html).toContain("削除する");
	});

	it("renders the not-found boundary for a missing capture", async () => {
		getCaptureFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/not-found",
					title: "Not found",
					status: 404,
					detail: "Capture was not found.",
					requestId: "request-404",
				},
			},
		});
		notFoundMock.mockImplementation(() => {
			throw new Error("NEXT_NOT_FOUND");
		});

		await expect(
			CaptureDetailPage({
				params: Promise.resolve({ captureId: "missing" }),
			}),
		).rejects.toThrow("NEXT_NOT_FOUND");
		expect(notFoundMock).toHaveBeenCalledOnce();
	});

	it("offers a way back to the captures list from the not-found view", () => {
		const html = renderToStaticMarkup(<CaptureNotFound />);

		expect(html).toContain("記録が見つかりません");
		expect(html).toContain('href="/captures"');
	});
});
