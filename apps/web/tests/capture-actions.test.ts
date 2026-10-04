import { beforeEach, describe, expect, it, vi } from "vitest";

const {
	createCaptureFromApiMock,
	listCapturesFromApiMock,
	notFoundMock,
	redirectMock,
	revalidatePathMock,
	updateCaptureFromApiMock,
} = vi.hoisted(() => ({
	createCaptureFromApiMock: vi.fn(),
	listCapturesFromApiMock: vi.fn(),
	notFoundMock: vi.fn(),
	redirectMock: vi.fn(),
	revalidatePathMock: vi.fn(),
	updateCaptureFromApiMock: vi.fn(),
}));

vi.mock("@/lib/api/capture", () => ({
	createCaptureFromApi: createCaptureFromApiMock,
	listCapturesFromApi: listCapturesFromApiMock,
	updateCaptureFromApi: updateCaptureFromApiMock,
}));
vi.mock("next/navigation", () => ({
	notFound: notFoundMock,
	redirect: redirectMock,
}));
vi.mock("next/cache", () => ({ revalidatePath: revalidatePathMock }));

import {
	createCaptureAction,
	listCapturesAction,
	updateCaptureAction,
} from "@/features/capture/actions";
import {
	initialCreateCaptureActionState,
	initialUpdateCaptureActionState,
} from "@/features/capture/capture-action-state";

function createFormData() {
	const formData = new FormData();
	formData.set("rawText", "牛乳を買う");
	formData.set("idempotencyKey", "capture-key");
	return formData;
}

describe("createCaptureAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("returns the created capture and revalidates the captures page", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "active",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T09:00:00Z",
		};
		createCaptureFromApiMock.mockResolvedValue({
			ok: true,
			data: capture,
		});

		const state = await createCaptureAction(
			initialCreateCaptureActionState,
			createFormData(),
		);

		expect(createCaptureFromApiMock).toHaveBeenCalledWith(
			"牛乳を買う",
			"capture-key",
		);
		expect(revalidatePathMock).toHaveBeenCalledWith("/captures");
		expect(state).toEqual({
			status: "success",
			data: capture,
			message: "記録しました。",
		});
	});

	it("maps the API rawText field error to the composer state", async () => {
		createCaptureFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/validation-error",
					title: "Validation error",
					status: 422,
					detail: "Request validation failed.",
					requestId: "request-422",
					errors: [
						{
							pointer: "/rawText",
							code: "string_too_long",
							detail: "2000文字以内で入力してください。",
						},
					],
				},
			},
		});

		const state = await createCaptureAction(
			initialCreateCaptureActionState,
			createFormData(),
		);

		expect(state).toEqual({
			status: "error",
			fieldErrors: {
				rawText: "2000文字以内で入力してください。",
			},
			message: "Request validation failed.（参照 ID: request-422）",
		});
		expect(revalidatePathMock).not.toHaveBeenCalled();
	});

	it("redirects unauthenticated failures without revalidating", async () => {
		createCaptureFromApiMock.mockResolvedValue({
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
			createCaptureAction(
				initialCreateCaptureActionState,
				createFormData(),
			),
		).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
		expect(revalidatePathMock).not.toHaveBeenCalled();
	});
});

describe("listCapturesAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("passes the cursor and preserves the response metadata", async () => {
		const response = {
			data: [
				{
					id: "capture-2",
					rawText: "資料を送る",
					status: "active",
					createdAt: "2026-10-04T08:00:00Z",
					updatedAt: "2026-10-04T08:00:00Z",
				},
			],
			meta: {
				nextCursor: "next-cursor",
				hasNextPage: true,
			},
		};
		listCapturesFromApiMock.mockResolvedValue({
			ok: true,
			data: response,
		});

		const state = await listCapturesAction("current-cursor");

		expect(listCapturesFromApiMock).toHaveBeenCalledWith({
			cursor: "current-cursor",
		});
		expect(state).toEqual({
			status: "success",
			data: response,
		});
	});

	it("rejects an empty cursor without calling the API", async () => {
		const state = await listCapturesAction("");

		expect(listCapturesFromApiMock).not.toHaveBeenCalled();
		expect(state).toEqual({
			status: "error",
			message: "カーソルが不正です。",
		});
	});

	it("converts API failures to an action error", async () => {
		listCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "network",
				message: "fetch failed",
			},
		});

		const state = await listCapturesAction("current-cursor");

		expect(state).toEqual({
			status: "error",
			message: "ネットワーク接続を確認して、もう一度お試しください。",
		});
	});

	it("returns an invalid cursor problem with its request ID", async () => {
		listCapturesFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/invalid-cursor",
					title: "Invalid cursor",
					status: 400,
					detail: "カーソルが不正です。",
					requestId: "request-400",
				},
			},
		});

		const state = await listCapturesAction("invalid-cursor");

		expect(state).toEqual({
			status: "error",
			message: "カーソルが不正です。（参照 ID: request-400）",
		});
	});

	it("redirects unauthenticated failures to login", async () => {
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

		await expect(
			listCapturesAction("current-cursor"),
		).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});
});

describe("updateCaptureAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("returns the updated capture and revalidates both pages", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買った",
			status: "active",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T10:00:00Z",
		};
		updateCaptureFromApiMock.mockResolvedValue({
			ok: true,
			data: capture,
		});
		const formData = new FormData();
		formData.set("rawText", "牛乳を買った");

		const state = await updateCaptureAction(
			"capture-1",
			initialUpdateCaptureActionState,
			formData,
		);

		expect(updateCaptureFromApiMock).toHaveBeenCalledWith(
			"capture-1",
			"牛乳を買った",
		);
		expect(revalidatePathMock).toHaveBeenCalledWith("/captures");
		expect(revalidatePathMock).toHaveBeenCalledWith("/captures/capture-1");
		expect(state).toEqual({
			status: "success",
			data: capture,
			message: "更新しました。",
		});
	});

	it("maps the API rawText field error to the editor state", async () => {
		updateCaptureFromApiMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/validation-error",
					title: "Validation error",
					status: 422,
					detail: "Request validation failed.",
					requestId: "request-422",
					errors: [
						{
							pointer: "/rawText",
							code: "string_too_long",
							detail: "2000文字以内で入力してください。",
						},
					],
				},
			},
		});

		const state = await updateCaptureAction(
			"capture-1",
			initialUpdateCaptureActionState,
			createFormData(),
		);

		expect(state).toEqual({
			status: "error",
			fieldErrors: {
				rawText: "2000文字以内で入力してください。",
			},
			message: "Request validation failed.（参照 ID: request-422）",
		});
		expect(revalidatePathMock).not.toHaveBeenCalled();
	});

	it("renders the not-found boundary when the capture no longer exists", async () => {
		updateCaptureFromApiMock.mockResolvedValue({
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
			updateCaptureAction(
				"missing",
				initialUpdateCaptureActionState,
				createFormData(),
			),
		).rejects.toThrow("NEXT_NOT_FOUND");
		expect(notFoundMock).toHaveBeenCalledOnce();
		expect(revalidatePathMock).not.toHaveBeenCalled();
	});

	it("redirects unauthenticated failures to login", async () => {
		updateCaptureFromApiMock.mockResolvedValue({
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
			updateCaptureAction(
				"capture-1",
				initialUpdateCaptureActionState,
				createFormData(),
			),
		).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});
});
