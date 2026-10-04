import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CaptureEmptyState } from "@/features/capture/capture-empty-state";
import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";
import { CapturePageFrame } from "@/features/capture/capture-page-frame";
import { CaptureComposerView } from "@/features/capture/capture-composer-view";
import { CaptureDetailEditorView } from "@/features/capture/capture-detail-editor";
import { CaptureList } from "@/features/capture/capture-list";
import { CaptureListPager } from "@/features/capture/capture-list-pager";

describe("Capture presentation", () => {
	it("renders the mobile composer with an accessible field error", () => {
		const html = renderToStaticMarkup(
			<CaptureComposerView
				defaultValue="牛乳を買う"
				fieldError="入力内容を確認してください"
			/>,
		);

		expect(html).toContain("何を残しますか");
		expect(html).toContain('name="rawText"');
		expect(html).toContain('aria-invalid="true"');
		expect(html).toContain("入力内容を確認してください");
		expect(html).toContain("記録する");
	});

	it("renders captures as a time-led list and escapes raw text", () => {
		const html = renderToStaticMarkup(
			<CaptureList
				items={[
					{
						id: "capture-1",
						href: "/captures/capture-1",
						timeLabel: "14:02",
						dateTime: "2026-10-02T05:02:00Z",
						rawText: "<script>alert('xss')</script>",
					},
				]}
			/>,
		);

		expect(html).toContain("<time");
		expect(html).toContain("14:02");
		expect(html).toContain("&lt;script&gt;");
		expect(html).not.toContain("<script>");
	});

	it("renders a directional empty state", () => {
		const html = renderToStaticMarkup(<CaptureEmptyState />);

		expect(html).toContain("最初の一文を書いてください");
	});

	it("renders an accessible list loading state", () => {
		const html = renderToStaticMarkup(<CaptureListSkeleton />);

		expect(html).toContain('aria-busy="true"');
		expect(html).toContain("記録を読み込んでいます");
	});

	it("renders the load-more control only when another page exists", () => {
		const item = {
			id: "capture-1",
			href: "/captures/capture-1",
			timeLabel: "14:02",
			dateTime: "2026-10-02T05:02:00Z",
			rawText: "牛乳を買う",
		};
		const withNextPage = renderToStaticMarkup(
			<CaptureListPager
				initialItems={[item]}
				initialNextCursor="next-cursor"
				initialHasNextPage
			/>,
		);
		const lastPage = renderToStaticMarkup(
			<CaptureListPager
				initialItems={[item]}
				initialNextCursor={null}
				initialHasNextPage={false}
			/>,
		);

		expect(withNextPage).toContain("牛乳を買う");
		expect(withNextPage).toContain("さらに表示");
		expect(lastPage).not.toContain("さらに表示");
	});

	it("renders detail editing and destructive actions separately", () => {
		const html = renderToStaticMarkup(
			<CaptureDetailEditorView
				defaultValue="牛乳を買う"
				timeLabel="10月2日 14:02"
			/>,
		);

		expect(html).toContain("保存する");
		expect(html).toContain("削除する");
		expect(html).toContain('name="rawText"');
	});

	it("keeps the composer in a distinct bottom region", () => {
		const html = renderToStaticMarkup(
			<CapturePageFrame dateLabel="10月2日 木" composer={<div>composer</div>}>
				<div>timeline</div>
			</CapturePageFrame>,
		);

		expect(html).toContain("10月2日 木");
		expect(html).toContain('data-slot="capture-composer-region"');
	});
});
