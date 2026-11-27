// @vitest-environment jsdom

import type { DigestReportResponse } from "@hibi/api-client";
import {
	act,
	cleanup,
	fireEvent,
	render,
	screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getLatestDigestReportActionMock, retryDigestReportActionMock } =
	vi.hoisted(() => ({
		getLatestDigestReportActionMock: vi.fn(),
		retryDigestReportActionMock: vi.fn(),
	}));

vi.mock("@/features/digest/actions", () => ({
	getLatestDigestReportAction: getLatestDigestReportActionMock,
	retryDigestReportAction: retryDigestReportActionMock,
}));

import { DigestReportCard } from "@/features/digest/digest-report-card";

function dailyReport(
	overrides: Partial<DigestReportResponse> = {},
): DigestReportResponse {
	return {
		id: "report-1",
		kind: "daily",
		periodStart: "2026-11-22",
		timezone: "Asia/Tokyo",
		status: "pending",
		content: null,
		contentVersion: "daily-digest-v1",
		errorCode: null,
		generatedAt: null,
		...overrides,
	};
}

const readyDaily = dailyReport({
	status: "ready",
	content: {
		items: [{ captureId: "capture-1", title: "牛乳", dueAt: null }],
		overdueCount: 0,
		dueTodayCount: 0,
		doneYesterdayCount: 2,
	},
	generatedAt: "2026-11-21T22:00:00Z",
});

const failedDaily = dailyReport({
	status: "failed",
	errorCode: "generation_failed",
});

async function clickRetry() {
	await act(async () => {
		fireEvent.click(screen.getByRole("button", { name: "もう一度作る" }));
	});
}

describe("DigestReportCard", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it("shows 作っています for a pending report", () => {
		render(<DigestReportCard report={dailyReport()} />);

		expect(screen.getByText("作っています")).toBeTruthy();
		expect(screen.queryByRole("button", { name: "もう一度作る" })).toBeNull();
	});

	it("shows the reason and a retry button for a failed report", () => {
		render(<DigestReportCard report={failedDaily} />);

		expect(screen.getByText("作れませんでした。")).toBeTruthy();
		expect(screen.getByRole("button", { name: "もう一度作る" })).toBeTruthy();
	});

	it("explains a provider failure of the weekly review", () => {
		render(
			<DigestReportCard
				report={dailyReport({
					kind: "weekly",
					contentVersion: "weekly-review-v1",
					status: "failed",
					errorCode: "review_provider_error",
				})}
			/>,
		);

		expect(
			screen.getByText("要約のサービスにつながらず、作れませんでした。"),
		).toBeTruthy();
	});

	it("treats an unknown error code as generation_failed", () => {
		// API に新しい理由が足されても、画面は壊れず、一般的な文を出す
		render(
			<DigestReportCard
				report={dailyReport({ status: "failed", errorCode: "new_reason" })}
			/>,
		);

		expect(screen.getByText("作れませんでした。")).toBeTruthy();
	});

	it("calls retryDigestReportAction and shows 作っています after success", async () => {
		retryDigestReportActionMock.mockResolvedValue({
			status: "success",
			data: dailyReport(),
			message: "もう一度作っています。",
		});
		render(<DigestReportCard report={failedDaily} />);

		await clickRetry();

		expect(retryDigestReportActionMock).toHaveBeenCalledWith("report-1");
		expect(screen.getByText("作っています")).toBeTruthy();
		expect(screen.queryByRole("button", { name: "もう一度作る" })).toBeNull();
	});

	it("shows the failure in an alert and keeps the retry button", async () => {
		retryDigestReportActionMock.mockResolvedValue({
			status: "error",
			message: "もう一度作れませんでした。",
		});
		render(<DigestReportCard report={failedDaily} />);

		await clickRetry();

		expect(screen.getByRole("alert").textContent).toBe(
			"もう一度作れませんでした。",
		);
		expect(screen.getByRole("button", { name: "もう一度作る" })).toBeTruthy();
	});

	it("polls a pending report every three seconds until it is ready", async () => {
		vi.useFakeTimers();
		getLatestDigestReportActionMock.mockResolvedValue({
			status: "success",
			data: readyDaily,
		});
		render(<DigestReportCard report={dailyReport()} />);

		expect(getLatestDigestReportActionMock).not.toHaveBeenCalled();
		await act(() => vi.advanceTimersByTimeAsync(3000));

		expect(getLatestDigestReportActionMock).toHaveBeenCalledWith("daily");
		expect(screen.getByText("牛乳")).toBeTruthy();
		expect(screen.getByText("昨日 2 件完了")).toBeTruthy();

		// ready になったら、もう読まない
		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getLatestDigestReportActionMock).toHaveBeenCalledOnce();
	});

	it("does not poll a ready report", async () => {
		vi.useFakeTimers();
		render(<DigestReportCard report={readyDaily} />);

		await act(() => vi.advanceTimersByTimeAsync(6000));

		expect(getLatestDigestReportActionMock).not.toHaveBeenCalled();
	});

	it("stops polling and shows the message when polling fails", async () => {
		vi.useFakeTimers();
		getLatestDigestReportActionMock.mockResolvedValue({
			status: "error",
			message: "ネットワーク接続を確認して、もう一度お試しください。",
		});
		render(<DigestReportCard report={dailyReport()} />);

		await act(() => vi.advanceTimersByTimeAsync(3000));
		expect(
			screen.getByText("ネットワーク接続を確認して、もう一度お試しください。"),
		).toBeTruthy();

		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getLatestDigestReportActionMock).toHaveBeenCalledOnce();
	});
});
