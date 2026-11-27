import { describe, expect, it } from "vitest";
import { getCurrentUser, getHealth } from "./index";
describe("generated API client", () => {
  it("endpoint関数を公開する", () => {
    expect(typeof getCurrentUser).toBe("function");
    expect(typeof getHealth).toBe("function");
  });
});