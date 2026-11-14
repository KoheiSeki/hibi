import { beforeEach, describe, expect, it, vi } from "vitest";

const {
	createCaptureMock,
	deleteCaptureMock,
	getCaptureMock,
	getServerApiContextMock,
	listTodayCapturesMock,
	markCaptureScenarioDoneMock,
	unmarkCaptureScenarioDoneMock,
	retryCaptureMock,
	updateCaptureMock,
	searchCapturesMock,
} = vi.hoisted(() => ({
	createCaptureMock: vi.fn(),
	deleteCaptureMock: vi.fn(),
	getCaptureMock: vi.fn(),
	getServerApiContextMock: vi.fn(),
	listTodayCapturesMock: vi.fn(),
	markCaptureScenarioDoneMock: vi.fn(),
	unmarkCaptureScenarioDoneMock: vi.fn(),
	retryCaptureMock: vi.fn(),
	updateCaptureMock: vi.fn(),
	searchCapturesMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@hibi/api-client", () => ({
	createCapture: createCaptureMock,
	deleteCapture: deleteCaptureMock,
	getCapture: getCaptureMock,
	listCaptures: vi.fn(),
	listTodayCaptures: listTodayCapturesMock,
	markCaptureScenarioDone: markCaptureScenarioDoneMock,
	unmarkCaptureScenarioDone: unmarkCaptureScenarioDoneMock,
	retryCapture: retryCaptureMock,
	updateCapture: updateCaptureMock,
	searchCaptures: searchCapturesMock,
}));
vi.mock("@/lib/api/server-context", () => ({
	getServerApiContext: getServerApiContextMock,
}));

import {
	createCaptureFromApi,
	deleteCaptureFromApi,
	getCaptureFromApi,
	listTodayCapturesFromApi,
	markCaptureScenarioDoneFromApi,
	unmarkCaptureScenarioDoneFromApi,
	retryCaptureFromApi,
	searchCapturesFromApi,
	updateCaptureFromApi,
} from "@/lib/api/capture";

describe("createCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("treats a 202 accepted response as a created capture", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "pending",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T09:00:00Z",
		};
		createCaptureMock.mockResolvedValue({
			data: {
				data: capture,
			},
			error: undefined,
			response: new Response(null, { status: 202 }),
		});

		const result = await createCaptureFromApi("牛乳を買う", "capture-key");

		expect(createCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			body: {
				rawText: "牛乳を買う",
			},
			headers: {
				"Idempotency-Key": "capture-key",
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

		const result = await createCaptureFromApi("牛乳を買う", "capture-key");

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

describe("updateCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("sends the capture ID and raw text through the generated client", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買った",
			status: "active",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T10:00:00Z",
		};
		updateCaptureMock.mockResolvedValue({
			data: {
				data: capture,
			},
		});

		const result = await updateCaptureFromApi("capture-1", "牛乳を買った");

		expect(updateCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			body: {
				rawText: "牛乳を買った",
			},
			path: {
				capture_id: "capture-1",
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

		const result = await updateCaptureFromApi("capture-1", "牛乳を買った");

		expect(updateCaptureMock).not.toHaveBeenCalled();
		expect(result.ok).toBe(false);
	});
});

describe("getCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("gets one capture through the generated client", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "processing",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T09:00:00Z",
		};
		getCaptureMock.mockResolvedValue({
			data: { data: capture },
		});

		const result = await getCaptureFromApi("capture-1");

		expect(getCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			path: {
				capture_id: "capture-1",
			},
		});
		expect(result).toEqual({ ok: true, data: capture });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await getCaptureFromApi("capture-1");

		expect(getCaptureMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});
});

describe("retryCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("retries a failed capture and normalizes the 202 response", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "pending",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T10:00:00Z",
		};
		retryCaptureMock.mockResolvedValue({
			data: { data: capture },
			error: undefined,
			response: new Response(null, { status: 202 }),
		});

		const result = await retryCaptureFromApi("capture-1");

		expect(retryCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			path: {
				capture_id: "capture-1",
			},
		});
		expect(result).toEqual({ ok: true, data: capture });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await retryCaptureFromApi("capture-1");

		expect(retryCaptureMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});
});

describe("deleteCaptureFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("sends the capture ID and treats an empty response as success", async () => {
		deleteCaptureMock.mockResolvedValue({
			data: undefined,
			error: undefined,
			response: new Response(null, { status: 204 }),
		});

		const result = await deleteCaptureFromApi("capture-1");

		expect(deleteCaptureMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			path: {
				capture_id: "capture-1",
			},
		});
		expect(result).toEqual({
			ok: true,
			data: undefined,
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

		const result = await deleteCaptureFromApi("capture-1");

		expect(deleteCaptureMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});
});

describe("searchCapturesFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("passes q and mode with the bearer token and unwraps the data array", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "completed",
			createdAt: "2026-10-04T09:00:00Z",
			updatedAt: "2026-10-04T09:00:00Z",
		};
		searchCapturesMock.mockResolvedValue({ data: { data: [capture] } });

		const result = await searchCapturesFromApi({ q: "牛乳", mode: "keyword" });

		expect(searchCapturesMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			query: { q: "牛乳", mode: "keyword" },
		});
		expect(result).toEqual({ ok: true, data: [capture] });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await searchCapturesFromApi({ q: "牛乳", mode: "semantic" });

		expect(searchCapturesMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});

	it("returns a classified error when the API responds with a failure", async () => {
		searchCapturesMock.mockResolvedValue({
			error: { title: "Service Unavailable", status: 503 },
			response: new Response(null, { status: 503 }),
		});

		const result = await searchCapturesFromApi({ q: "牛乳", mode: "keyword" });

		expect(result.ok).toBe(false);
	});
});

describe("listTodayCapturesFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("passes the limit with the bearer token and unwraps the data array", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "completed",
			createdAt: "2026-11-10T05:00:00Z",
			updatedAt: "2026-11-10T05:00:00Z",
		};
		listTodayCapturesMock.mockResolvedValue({ data: { data: [capture] } });

		const result = await listTodayCapturesFromApi({ limit: 3 });

		expect(listTodayCapturesMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			query: { limit: 3 },
		});
		expect(result).toEqual({ ok: true, data: [capture] });
	});

	it("works without arguments", async () => {
		listTodayCapturesMock.mockResolvedValue({ data: { data: [] } });

		const result = await listTodayCapturesFromApi();

		expect(listTodayCapturesMock).toHaveBeenCalledOnce();
		expect(result).toEqual({ ok: true, data: [] });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await listTodayCapturesFromApi();

		expect(listTodayCapturesMock).not.toHaveBeenCalled();
		expect(result).toEqual({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
	});
});

describe.each([
	{
		name: "markCaptureScenarioDoneFromApi",
		call: markCaptureScenarioDoneFromApi,
		mock: markCaptureScenarioDoneMock,
	},
	{
		name: "unmarkCaptureScenarioDoneFromApi",
		call: unmarkCaptureScenarioDoneFromApi,
		mock: unmarkCaptureScenarioDoneMock,
	},
])("$name", ({ call, mock }) => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("calls the API for the capture and unwraps the capture", async () => {
		const capture = {
			id: "capture-1",
			rawText: "牛乳を買う",
			status: "completed",
			createdAt: "2026-11-10T05:00:00Z",
			updatedAt: "2026-11-10T05:00:00Z",
		};
		mock.mockResolvedValue({ data: { data: capture } });

		const result = await call("capture-1");

		expect(mock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			path: { capture_id: "capture-1" },
		});
		expect(result).toEqual({ ok: true, data: capture });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});

		const result = await call("capture-1");

		expect(mock).not.toHaveBeenCalled();
		expect(result.ok).toBe(false);
	});
});
