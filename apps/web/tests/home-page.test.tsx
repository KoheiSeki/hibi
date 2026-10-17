import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { createClientMock, redirectMock } = vi.hoisted(() => ({
	createClientMock: vi.fn(),
	redirectMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/auth/server", () => ({ createClient: createClientMock }));

import HomePage from "@/app/page";

describe("HomePage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("redirects a signed-in user to the captures page", async () => {
		createClientMock.mockResolvedValue({
			auth: {
				getUser: vi.fn().mockResolvedValue({
					data: { user: { id: "user-1" } },
				}),
			},
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(HomePage()).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/captures");
	});

	it("shows the introduction card when nobody is signed in", async () => {
		createClientMock.mockResolvedValue({
			auth: {
				getUser: vi.fn().mockResolvedValue({
					data: { user: null },
				}),
			},
		});

		const html = renderToStaticMarkup(await HomePage());

		expect(html).toContain("ログイン");
		expect(redirectMock).not.toHaveBeenCalled();
	});
});
