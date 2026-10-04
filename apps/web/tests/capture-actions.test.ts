import { beforeEach, describe, expect, it, vi } from "vitest";

const { createCaptureFromApiMock, redirectMock, revalidatePathMock } =
	vi.hoisted(() => ({
		createCaptureFromApiMock: vi.fn(),
		redirectMock: vi.fn(),
		revalidatePathMock: vi.fn(),
	}));

vi.mock("@/lib/api/capture", () => ({
	createCaptureFromApi: createCaptureFromApiMock,
}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("next/cache", () => ({ revalidatePath: revalidatePathMock }));

import { createCaptureAction } from "@/features/capture/actions";
import { initialCreateCaptureActionState } from "@/features/capture/capture-action-state";

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
