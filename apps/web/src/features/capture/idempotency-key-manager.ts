type CreateIdempotencyKey = () => string;

export type IdempotencyKeyManager = {
	applyTo(formData: FormData): void;
	reset(): void;
};

export function createIdempotencyKeyManager(
	createKey: CreateIdempotencyKey = () => crypto.randomUUID(),
): IdempotencyKeyManager {
	let currentKey: string | null = null;

	return {
		applyTo(formData) {
			currentKey ??= createKey();
			formData.set("idempotencyKey", currentKey);
		},
		reset() {
			currentKey = null;
		},
	};
}
