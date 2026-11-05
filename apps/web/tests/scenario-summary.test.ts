import { describe, expect, it } from "vitest";

import { scenarioSummary } from "@/features/capture/scenario-summary";

describe("scenarioSummary", () => {
	it("keeps a title when there is no amount or reminder", () => {
		expect(
			scenarioSummary({
				route: "shopping",
				status: "proposed",
				title: "牛乳",
				policyVersion: "capture-scenario-v1",
			}),
		).toBe("牛乳");
	});

	it("appends a localized yen amount", () => {
		expect(
			scenarioSummary({
				route: "expense",
				status: "proposed",
				title: "ランチ",
				amount: 1200,
				policyVersion: "capture-scenario-v1",
			}),
		).toBe("ランチ 1,200円");
	});

	it("appends reminder text", () => {
		expect(
			scenarioSummary({
				route: "reminder",
				status: "proposed",
				title: "起こして",
				remindText: "明日の 9 時",
				policyVersion: "capture-scenario-v1",
			}),
		).toBe("起こして 明日の 9 時");
	});
});
