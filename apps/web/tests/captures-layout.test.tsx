import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
	Noto_Sans_JP: () => ({ variable: "font-body" }),
	Shippori_Mincho: () => ({ variable: "font-display" }),
}));

import CapturesLayout from "@/app/captures/layout";

describe("CapturesLayout", () => {
	it("links the home, today, digest and account pages in the header", () => {
		const html = renderToStaticMarkup(
			<CapturesLayout>
				<div>child</div>
			</CapturesLayout>,
		);

		expect(html).toContain('href="/captures"');
		expect(html).toContain('href="/captures/today"');
		expect(html).toContain("今日");
		expect(html).toContain('href="/captures/digest"');
		expect(html).toContain("ダイジェスト");
		expect(html).toContain('href="/account"');
		expect(html).toContain("child");
	});
});
