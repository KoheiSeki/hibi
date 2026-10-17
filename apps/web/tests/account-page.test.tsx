import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { createClientMock, getCurrentUserMock, redirectMock } = vi.hoisted(
	() => ({
		createClientMock: vi.fn(),
		getCurrentUserMock: vi.fn(),
		redirectMock: vi.fn(),
	}),
);

vi.mock("next/font/google", () => ({
	Noto_Sans_JP: () => ({ variable: "--font-capture-body" }),
	Shippori_Mincho: () => ({ variable: "--font-capture-display" }),
}));
vi.mock("next/navigation", () => ({ redirect: redirectMock }));
vi.mock("@/lib/auth/server", () => ({ createClient: createClientMock }));
vi.mock("@/lib/api/server", () => ({
	getCurrentUserFromApi: getCurrentUserMock,
}));

import AccountPage from "@/app/account/page";

const user = {
	id: "11111111-1111-4111-8111-111111111111",
	email: "week2@example.com",
};

function mockAuthenticatedUser() {
	createClientMock.mockResolvedValue({
		auth: {
			getUser: vi.fn().mockResolvedValue({ data: { user } }),
		},
	});
}

describe("AccountPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		mockAuthenticatedUser();
	});

	it("renders a logout control for an authenticated user", async () => {
		getCurrentUserMock.mockResolvedValue({
			ok: true,
			data: { userId: user.id },
		});

		const html = renderToStaticMarkup(await AccountPage());

		expect(html).toContain("ログアウト");
	});

	it("renders network errors without redirecting to login", async () => {
		getCurrentUserMock.mockResolvedValue({
			ok: false,
			error: { kind: "network", message: "fetch failed" },
		});

		const html = renderToStaticMarkup(await AccountPage());

		expect(html).toContain("通信に失敗しました");
		expect(redirectMock).not.toHaveBeenCalled();
	});

	it("renders API 401 problems without redirecting to login", async () => {
		getCurrentUserMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/unauthorized",
					title: "Unauthorized",
					status: 401,
					detail: "Authentication is required.",
					requestId: "req-401",
				},
			},
		});

		const html = renderToStaticMarkup(await AccountPage());

		expect(html).toContain("認証に失敗しました");
		expect(redirectMock).not.toHaveBeenCalled();
	});

	it("renders API 500 problems without redirecting to login", async () => {
		getCurrentUserMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "problem",
				problem: {
					type: "https://api.hibi.example/problems/internal-error",
					title: "Internal server error",
					status: 500,
					detail: "An unexpected error occurred.",
					requestId: "req-500",
				},
			},
		});

		const html = renderToStaticMarkup(await AccountPage());

		expect(html).toContain("サーバーで問題が発生しました");
		expect(redirectMock).not.toHaveBeenCalled();
	});

	it("redirects only client-side unauthenticated failures to login", async () => {
		getCurrentUserMock.mockResolvedValue({
			ok: false,
			error: {
				kind: "unauthenticated",
				message: "Authentication is required.",
			},
		});
		redirectMock.mockImplementation(() => {
			throw new Error("NEXT_REDIRECT");
		});

		await expect(AccountPage()).rejects.toThrow("NEXT_REDIRECT");
		expect(redirectMock).toHaveBeenCalledWith("/login");
	});
});
