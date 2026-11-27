import { describe, expect, it } from "vitest";

import { formatJstDueLabel } from "@/lib/date-time";

// 2026-11-10 15:00 JST
const NOW = new Date("2026-11-10T06:00:00Z");

describe("formatJstDueLabel", () => {
  it.each([
    ["2026-11-10T00:30:00Z", "09:30"],
    ["2026-11-09T00:00:00Z", "昨日 09:00"],
    ["2026-11-11T00:00:00Z", "明日 09:00"],
    ["2026-11-07T00:00:00Z", "11/07 09:00"],
    // UTC では 11/10 だが JST では 11/11 0:00
    ["2026-11-10T15:00:00Z", "明日 00:00"],
  ])("formats %s as %s", (timestamp, expected) => {
    expect(formatJstDueLabel(timestamp, NOW)).toBe(expected);
  });

  it("rejects an invalid timestamp", () => {
    expect(() => formatJstDueLabel("not-a-date", NOW)).toThrow(RangeError);
  });
});
