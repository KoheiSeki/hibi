import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { requireUserMock } = vi.hoisted(() => ({
	requireUserMock: vi.fn(),
}));

vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth/require-user", () => ({ requireUser: requireUserMock }));
vi.mock("@/features/capture/today-section", () => ({
	TodaySection: () => <div>today-rows</div>,
}));

import TodayPage from "@/app/captures/today/page";

describe("TodayPage", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("requires a signed-in user and renders the today section", async () => {
		const html = renderToStaticMarkup(await TodayPage());

		expect(requireUserMock).toHaveBeenCalledOnce();
		expect(html).toContain("today-rows");
	});
});
