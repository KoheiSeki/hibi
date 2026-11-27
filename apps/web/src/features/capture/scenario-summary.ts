import type { ScenarioResponse } from "@hibi/api-client";

export function scenarioSummary(scenario: ScenarioResponse): string {
	const parts = [scenario.title];
	if (scenario.amount != null) {
		parts.push(`${scenario.amount.toLocaleString("ja-JP")}円`);
	}
	if (scenario.remindText) {
		parts.push(scenario.remindText);
	}
	return parts.join(" ");
}
