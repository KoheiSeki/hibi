import { parseCaptureSearchParams } from "@/features/capture/capture-search-params";
import { describe, expect, it } from "vitest";

describe("parseCaptureSearchParams", () => {
	it("returns keyword mode by default", () => {
		expect(parseCaptureSearchParams({ q: "牛乳" })).toEqual({
			q: "牛乳",
			mode: "keyword",
		});
	});

	it("trims q and accepts semantic", () => {
		expect(
			parseCaptureSearchParams({ q: "  ミルク ", mode: "semantic" }),
		).toEqual({ q: "ミルク", mode: "semantic" });
	});

	it("returns null when q is missing or blank", () => {
		expect(parseCaptureSearchParams({})).toBeNull();
		expect(parseCaptureSearchParams({ q: "   " })).toBeNull();
	});

	it("accepts exactly 200 characters and rejects 201", () => {
		expect(parseCaptureSearchParams({ q: "あ".repeat(200) })).not.toBeNull();
		expect(parseCaptureSearchParams({ q: "あ".repeat(201) })).toBeNull();
	});

	it("falls back to keyword for an unknown mode", () => {
		expect(parseCaptureSearchParams({ q: "牛乳", mode: "bogus" })?.mode).toBe(
			"keyword",
		);
	});

	it("uses the first value when a parameter is repeated", () => {
		expect(
			parseCaptureSearchParams({
				q: ["牛乳", "記事"],
				mode: ["semantic", "keyword"],
			}),
		).toEqual({ q: "牛乳", mode: "semantic" });
	});
});
