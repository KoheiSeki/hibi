import { beforeEach, describe, expect, it, vi } from "vitest";

const { createClientMock, redirectMock, signInMock } = vi.hoisted(() => ({
	createClientMock: vi.fn(),
	redirectMock: vi.fn(),
	signInMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/auth/server", () => ({ createClient: createClientMock }));

import { signInAction } from "@/app/login/actions";

function createFormData() {
	const formData = new FormData();
	formData.set("email", "week3@example.com");
	formData.set("password", "password");
	return formData;
}

describe("signInAction", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		createClientMock.mockResolvedValue({
			auth: { signInWithPassword: signInMock },
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});
	});

	it("redirects a successful sign-in to the captures page", async () => {
		signInMock.mockResolvedValue({ error: null });

		await expect(signInAction(createFormData())).rejects.toThrow(
			"NEXT_REDIRECT",
		);
		expect(signInMock).toHaveBeenCalledWith({
			email: "week3@example.com",
			password: "password",
		});
		expect(redirectMock).toHaveBeenCalledWith("/captures");
	});

	it("returns invalid credentials to the login page", async () => {
		signInMock.mockResolvedValue({ error: new Error("invalid") });

		await expect(signInAction(createFormData())).rejects.toThrow(
			"NEXT_REDIRECT",
		);
		expect(redirectMock).toHaveBeenCalledWith(
			"/login?error=invalid-credentials",
		);
	});
});
