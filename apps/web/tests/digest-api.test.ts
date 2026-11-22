import { beforeEach, describe, expect, it, vi } from "vitest";

const { getServerApiContextMock, listDigestReportsMock, retryDigestReportMock } =
	vi.hoisted(() => ({
		getServerApiContextMock: vi.fn(),
		listDigestReportsMock: vi.fn(),
		retryDigestReportMock: vi.fn(),
	}));

vi.mock("server-only", () => ({}));
vi.mock("@hibi/api-client", () => ({
	listDigestReports: listDigestReportsMock,
	retryDigestReport: retryDigestReportMock,
}));
vi.mock("@/lib/api/server-context", () => ({
	getServerApiContext: getServerApiContextMock,
}));

import {
	listDigestReportsFromApi,
	retryDigestReportFromApi,
} from "@/lib/api/digest";

const report = {
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

describe("listDigestReportsFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("passes kind and limit and unwraps the data array", async () => {
		listDigestReportsMock.mockResolvedValue({
			data: { data: [report] },
			error: undefined,
			response: new Response(null, { status: 200 }),
		});

		const result = await listDigestReportsFromApi({ kind: "daily", limit: 1 });

		expect(listDigestReportsMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			query: { kind: "daily", limit: 1 },
		});
		expect(result).toEqual({ ok: true, data: [report] });
	});

	it("leaves kind and limit to the API defaults when omitted", async () => {
		listDigestReportsMock.mockResolvedValue({
			data: { data: [] },
			error: undefined,
			response: new Response(null, { status: 200 }),
		});

		const result = await listDigestReportsFromApi();

		expect(listDigestReportsMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			query: { kind: undefined, limit: undefined },
		});
		expect(result).toEqual({ ok: true, data: [] });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue(unauthenticated);

		const result = await listDigestReportsFromApi({ kind: "daily", limit: 1 });

		expect(listDigestReportsMock).not.toHaveBeenCalled();
		expect(result).toEqual(unauthenticated);
	});
});

describe("retryDigestReportFromApi", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		getServerApiContextMock.mockResolvedValue({
			ok: true,
			baseUrl: "https://api.hibi.example",
			accessToken: "access-token",
		});
	});

	it("retries a report by id and treats 202 as success", async () => {
		retryDigestReportMock.mockResolvedValue({
			data: { data: report },
			error: undefined,
			response: new Response(null, { status: 202 }),
		});

		const result = await retryDigestReportFromApi("report-1");

		expect(retryDigestReportMock).toHaveBeenCalledWith({
			baseUrl: "https://api.hibi.example",
			auth: "access-token",
			path: { report_id: "report-1" },
		});
		expect(result).toEqual({ ok: true, data: report });
	});

	it("does not call the API without an authenticated context", async () => {
		getServerApiContextMock.mockResolvedValue(unauthenticated);

		const result = await retryDigestReportFromApi("report-1");

		expect(retryDigestReportMock).not.toHaveBeenCalled();
		expect(result).toEqual(unauthenticated);
	});
});
