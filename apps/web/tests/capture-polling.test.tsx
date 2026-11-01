// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { CaptureResponse } from "@hibi/api-client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
	deleteCaptureActionMock,
	getCaptureActionMock,
	listCapturesActionMock,
	retryCaptureActionMock,
	updateCaptureActionMock,
} = vi.hoisted(() => ({
	deleteCaptureActionMock: vi.fn(),
	getCaptureActionMock: vi.fn(),
	listCapturesActionMock: vi.fn(),
	retryCaptureActionMock: vi.fn(),
	updateCaptureActionMock: vi.fn(),
}));

vi.mock("@/features/capture/actions", () => ({
	deleteCaptureAction: deleteCaptureActionMock,
	getCaptureAction: getCaptureActionMock,
	listCapturesAction: listCapturesActionMock,
	retryCaptureAction: retryCaptureActionMock,
	updateCaptureAction: updateCaptureActionMock,
}));

import {
	captureStatusMessage,
	isCaptureProcessing,
} from "@/features/capture/capture-processing-status";
import { CaptureDetailEditor } from "@/features/capture/capture-detail-editor";
import { CaptureListPager } from "@/features/capture/capture-list-pager";
import { useCapturePolling } from "@/features/capture/use-capture-polling";

const capture: CaptureResponse = {
	id: "capture-1",
	rawText: "牛乳を買う",
	status: "processing",
	createdAt: "2026-10-04T09:00:00Z",
	updatedAt: "2026-10-04T09:00:00Z",
};

function PollingHarness({
	captureIds,
	onCapture,
}: {
	captureIds: readonly string[];
	onCapture: (capture: CaptureResponse) => void;
}) {
	const { error, retryPolling } = useCapturePolling({
		captureIds,
		onCapture,
	});

	return (
		<>
			{error ? <p>{error}</p> : null}
			<button type="button" onClick={retryPolling}>
				もう一度確認
			</button>
		</>
	);
}

describe("capture processing status", () => {
	it.each(["pending", "processing"])(
		"treats %s as an in-progress status",
		(status) => {
			expect(isCaptureProcessing(status)).toBe(true);
			expect(captureStatusMessage(status)).toBe("整えています");
		},
	);

	it("shows retry copy only for failed captures", () => {
		expect(isCaptureProcessing("failed")).toBe(false);
		expect(captureStatusMessage("failed")).toBe("やり直せます");
		expect(captureStatusMessage("completed")).toBeUndefined();
		expect(captureStatusMessage("unknown")).toBeUndefined();
	});
});

describe("useCapturePolling", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it("polls each unfinished capture after three seconds", async () => {
		const onCapture = vi.fn();
		getCaptureActionMock.mockResolvedValue({
			status: "success",
			data: capture,
		});
		render(
			<PollingHarness
				captureIds={["capture-1", "capture-2"]}
				onCapture={onCapture}
			/>,
		);

		expect(getCaptureActionMock).not.toHaveBeenCalled();
		await act(() => vi.advanceTimersByTimeAsync(3000));

		expect(getCaptureActionMock).toHaveBeenCalledTimes(2);
		expect(getCaptureActionMock).toHaveBeenNthCalledWith(1, "capture-1");
		expect(getCaptureActionMock).toHaveBeenNthCalledWith(2, "capture-2");
		expect(onCapture).toHaveBeenCalledTimes(2);
	});

	it("stops after an error and resumes immediately on demand", async () => {
		getCaptureActionMock
			.mockResolvedValueOnce({
				status: "error",
				message: "状態を取得できませんでした。",
			})
			.mockResolvedValueOnce({
				status: "success",
				data: capture,
			});
		const onCapture = vi.fn();
		render(
			<PollingHarness captureIds={["capture-1"]} onCapture={onCapture} />,
		);

		await act(() => vi.advanceTimersByTimeAsync(3000));
		expect(screen.getByText("状態を取得できませんでした。")).toBeTruthy();

		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getCaptureActionMock).toHaveBeenCalledOnce();

		await act(async () => {
			screen.getByRole("button", { name: "もう一度確認" }).click();
			await vi.advanceTimersByTimeAsync(0);
		});
		expect(getCaptureActionMock).toHaveBeenCalledTimes(2);
		expect(onCapture).toHaveBeenCalledWith(capture);
	});

	it("stops after a thrown polling failure", async () => {
		getCaptureActionMock.mockRejectedValue(new Error("NEXT_REDIRECT"));
		render(
			<PollingHarness captureIds={["capture-1"]} onCapture={vi.fn()} />,
		);

		await act(() => vi.advanceTimersByTimeAsync(3000));
		expect(screen.getByText("状態を取得できませんでした。")).toBeTruthy();
		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getCaptureActionMock).toHaveBeenCalledOnce();
	});

	it("does not publish an in-flight result after unmount", async () => {
		let resolveAction:
			| ((value: { status: "success"; data: CaptureResponse }) => void)
			| undefined;
		getCaptureActionMock.mockReturnValue(
			new Promise((resolve) => {
				resolveAction = resolve;
			}),
		);
		const onCapture = vi.fn();
		const view = render(
			<PollingHarness captureIds={["capture-1"]} onCapture={onCapture} />,
		);

		await act(() => vi.advanceTimersByTimeAsync(3000));
		view.unmount();
		await act(async () => {
			resolveAction?.({ status: "success", data: capture });
			await Promise.resolve();
		});

		expect(onCapture).not.toHaveBeenCalled();
	});
});

describe("CaptureListPager polling", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it("polls only unfinished rows and updates the completed row in place", async () => {
		getCaptureActionMock.mockResolvedValue({
			status: "success",
			data: {
				...capture,
				status: "completed",
			},
		});
		render(
			<CaptureListPager
				initialItems={[
					{
						id: "capture-1",
						href: "/captures/capture-1",
						rawText: "牛乳を買う",
						status: "processing",
						timeLabel: "18:00",
						dateTime: "2026-10-04T09:00:00Z",
					},
					{
						id: "capture-2",
						href: "/captures/capture-2",
						rawText: "資料を送る",
						status: "completed",
						timeLabel: "17:00",
						dateTime: "2026-10-04T08:00:00Z",
					},
				]}
				initialNextCursor={null}
				initialHasNextPage={false}
			/>,
		);

		expect(screen.getByText("整えています")).toBeTruthy();
		await act(() => vi.advanceTimersByTimeAsync(3000));

		expect(getCaptureActionMock).toHaveBeenCalledOnce();
		expect(getCaptureActionMock).toHaveBeenCalledWith("capture-1");
		expect(screen.queryByText("整えています")).toBeNull();

		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getCaptureActionMock).toHaveBeenCalledOnce();
	});

	it("shows failed copy without polling the row", async () => {
		render(
			<CaptureListPager
				initialItems={[
					{
						id: "capture-1",
						href: "/captures/capture-1",
						rawText: "牛乳を買う",
						status: "failed",
						timeLabel: "18:00",
						dateTime: "2026-10-04T09:00:00Z",
					},
				]}
				initialNextCursor={null}
				initialHasNextPage={false}
			/>,
		);

		expect(screen.getByText("やり直せます")).toBeTruthy();
		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getCaptureActionMock).not.toHaveBeenCalled();
	});
});

describe("CaptureDetailEditor polling", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.clearAllMocks();
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it("removes processing copy and stops polling after completion", async () => {
		getCaptureActionMock.mockResolvedValue({
			status: "success",
			data: {
				...capture,
				status: "completed",
			},
		});
		render(
			<CaptureDetailEditor
				captureId="capture-1"
				defaultValue="牛乳を買う"
				initialStatus="processing"
				timeLabel="10月4日 18:00"
			/>,
		);

		expect(screen.getByText("整えています")).toBeTruthy();
		expect(
			screen.getByRole("button", { name: "保存する" }).hasAttribute("disabled"),
		).toBe(true);

		await act(() => vi.advanceTimersByTimeAsync(3000));

		expect(screen.queryByText("整えています")).toBeNull();
		await act(() => vi.advanceTimersByTimeAsync(6000));
		expect(getCaptureActionMock).toHaveBeenCalledOnce();
	});

	it("retries a failed capture and starts polling the returned pending state", async () => {
		retryCaptureActionMock.mockResolvedValue({
			status: "success",
			data: {
				...capture,
				status: "pending",
			},
			message: "もう一度整えています。",
		});
		getCaptureActionMock.mockResolvedValue({
			status: "success",
			data: {
				...capture,
				status: "processing",
			},
		});
		render(
			<CaptureDetailEditor
				captureId="capture-1"
				defaultValue="牛乳を買う"
				initialStatus="failed"
				timeLabel="10月4日 18:00"
			/>,
		);

		expect(screen.getByText("やり直せます")).toBeTruthy();
		fireEvent.click(screen.getByRole("button", { name: "もう一度整える" }));
		await act(async () => {
			await Promise.resolve();
		});

		expect(retryCaptureActionMock).toHaveBeenCalledWith("capture-1");
		expect(screen.getByText("整えています")).toBeTruthy();
		await act(() => vi.advanceTimersByTimeAsync(3000));
		expect(getCaptureActionMock).toHaveBeenCalledWith("capture-1");
	});
});
