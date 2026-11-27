import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CaptureSearchForm } from "@/features/capture/capture-search-form";

function radioTag(html: string, value: string): string {
	const tag = html.match(
		new RegExp(`<input type="radio"[^>]*value="${value}"[^>]*/>`),
	);
	if (!tag) {
		throw new Error(`radio ${value} not found`);
	}
	return tag[0];
}

describe("CaptureSearchForm", () => {
	it("renders a GET search form to /captures", () => {
		const html = renderToStaticMarkup(
			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
		);

		expect(html).toContain('role="search"');
		expect(html).toContain('method="get"');
		expect(html).toContain('action="/captures"');
	});

	it("renders the query input limited to 200 characters", () => {
		const html = renderToStaticMarkup(
			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
		);

		expect(html).toContain('name="q"');
		expect(html).toContain('maxLength="200"');
		expect(html).toContain('aria-label="記録を検索"');
	});

	it("offers keyword and semantic modes and checks the default", () => {
		const html = renderToStaticMarkup(
			<CaptureSearchForm defaultQuery="" defaultMode="keyword" />,
		);

		expect(html).toContain("キーワード");
		expect(html).toContain("意味");
		expect(radioTag(html, "keyword")).toContain("checked");
		expect(radioTag(html, "semantic")).not.toContain("checked");
	});

	it("reflects the current search", () => {
		const html = renderToStaticMarkup(
			<CaptureSearchForm defaultQuery="牛乳" defaultMode="semantic" />,
		);

		expect(html).toContain('value="牛乳"');
		expect(radioTag(html, "semantic")).toContain("checked");
		expect(radioTag(html, "keyword")).not.toContain("checked");
	});
});