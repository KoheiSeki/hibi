import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requireUserMock } = vi.hoisted(() => ({
	requireUserMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/require-user", () => ({ requireUser: requireUserMock }));
vi.mock("@/features/digest/digest-section", () => ({
	DigestSection: () => <div>digest-cards</div>,
}));

import DigestPage from "@/app/captures/digest/page";

describe("DigestPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("requires a signed-in user and renders the digest section", async () => {
		const html = renderToStaticMarkup(await DigestPage());

		expect(requireUserMock).toHaveBeenCalledOnce();
		expect(html).toContain("ダイジェスト");
		expect(html).toContain("digest-cards");
	});
});
