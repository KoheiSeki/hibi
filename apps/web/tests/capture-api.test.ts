import { beforeEach, describe, expect, it, vi } from "vitest";

const { createCaptureMock, getServerApiContextMock } = vi.hoisted(() => ({
	createCaptureMock: vi.fn(),
	getServerApiContextMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@hibi/api-client", () => ({
	createCapture: createCaptureMock,
	listCaptures: vi.fn(),
}));
vi.mock("@/lib/api/server-context", () => ({
	getServerApiContext: getServerApiContextMock,
}));

import { createCaptureFromApi } from "@/lib/api/capture";

describe("createCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("sends the raw text and idempotency key through the generated client", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "active",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T09:00:00Z",
		};
		createCaptureMock.mockResolvedValue({
			data: {
				data: capture,
			},
		});

		const result = await createCaptureFromApi(
			"牛乳を買う",
			"capture-key",
		);

		expect(createCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			body: {
				rawText: "牛乳を買う",
			},
			headers: {
				idempotencyKey: "capture-key",
			},
		});
		expect(result).toEqual({
			ok: true,
			data: capture,
		});
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await createCaptureFromApi(
			"牛乳を買う",
			"capture-key",
		);

		expect(createCaptureMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});
});
