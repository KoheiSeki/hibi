import Link from "next/link";

export default function CaptureNotFound() {
	return (
		<main className="mx-auto flex min-h-[calc(100svh-3.5rem)] w-full max-w-2xl items-center px-5 py-12 sm:px-8">
			<div className="w-full border-y border-[#D5DCE5] py-12 text-center">
				<p className="text-xs font-medium tracking-[0.08em] text-[#4A5870]">
					404
				</p>
				<h1 className="mt-3 text-xl font-semibold tracking-[-0.02em] text-[#1A1D23]">
					記録が見つかりません
				</h1>
				<p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-[#4A5870]">
					削除されたか、表示できない記録です。一覧から別の記録を選んでください。
				</p>
				<Link
					href="/captures"
					className="mt-7 inline-flex h-11 items-center justify-center rounded-full border border-[#BFC8D3] px-6 text-sm font-semibold text-[#1A1D23] no-underline outline-none transition-colors hover:bg-white focus-visible:ring-2 focus-visible:ring-[#2F6A4A]"
				>
					一覧へ戻る
				</Link>
			</div>
		</main>
	);
}
