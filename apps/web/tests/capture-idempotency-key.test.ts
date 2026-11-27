import { createIdempotencyKeyManager } from "@/features/capture/idempotency-key-manager";
import { describe, expect, it, vi } from "vitest";

describe("Capture idempotency key", () => {
	it("reuses the key until the capture succeeds", () => {
		const createKey = vi
			.fn()
			.mockReturnValueOnce("capture-key-1")
			.mockReturnValueOnce("capture-key-2");
		const manager = createIdempotencyKeyManager(createKey);
		const firstAttempt = new FormData();
		const retryAttempt = new FormData();

		manager.applyTo(firstAttempt);
		manager.applyTo(retryAttempt);

		expect(firstAttempt.get("idempotencyKey")).toBe("capture-key-1");
		expect(retryAttempt.get("idempotencyKey")).toBe("capture-key-1");
		expect(createKey).toHaveBeenCalledTimes(1);
	});

	it("creates a new key after a successful capture", () => {
		const createKey = vi
			.fn()
			.mockReturnValueOnce("capture-key-1")
			.mockReturnValueOnce("capture-key-2");
		const manager = createIdempotencyKeyManager(createKey);
		const firstCapture = new FormData();
		const nextCapture = new FormData();

		manager.applyTo(firstCapture);
		manager.reset();
		manager.applyTo(nextCapture);

		expect(firstCapture.get("idempotencyKey")).toBe("capture-key-1");
		expect(nextCapture.get("idempotencyKey")).toBe("capture-key-2");
	});
});
