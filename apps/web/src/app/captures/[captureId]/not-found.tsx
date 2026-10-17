import Link from "next/link";

export default function CaptureNotFound() {
	return (
		<main className="mx-auto flex min-h-[calc(100svh-3.5rem)] w-full max-w-2xl items-center px-5 py-12 sm:px-8">
			<div className="w-full py-12 text-center">
				<span
					aria-hidden="true"
					className="mx-auto mb-5 block size-2.5 rounded-full bg-[#1E6B43] ring-4 ring-[#D5E3D9]"
				/>
				<h1 className="text-[1.65rem] font-medium tracking-[0.04em] text-[#15201A] [font-family:var(--font-capture-display),serif]">
					記録が見つかりません
				</h1>
				<p className="mx-auto mt-3 max-w-sm text-sm leading-6 text-[#5A6A62]">
					削除されたか、表示できない記録です。一覧から別の記録を選んでください。
				</p>
				<Link
					href="/captures"
					className="mt-7 inline-flex h-11 items-center justify-center rounded-full bg-[#1E6B43] px-6 text-sm font-semibold text-white no-underline outline-none transition-colors hover:bg-[#185838] focus-visible:ring-2 focus-visible:ring-[#1E6B43]"
				>
					一覧へ戻る
				</Link>
			</div>
		</main>
	);
}
