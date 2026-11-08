import type { ReactNode } from "react";

/** 検索結果が 0 件のときの、糸の最初の節。 */
export function CaptureSearchEmptyState(): ReactNode {
	return (
		<div className="flex min-h-40 items-center px-2">
			<div className="grid grid-cols-[1.15rem_minmax(0,1fr)] items-start gap-3">
				<span
					aria-hidden="true"
					className="mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF]"
				/>
				<div>
					<p className="text-base font-semibold text-[#15201A]">
						見つかりませんでした
					</p>
					<p className="mt-2 text-sm leading-6 text-[#5A6A62]">
						言葉を変えるか、検索方法を切り替えてみてください。
					</p>
				</div>
			</div>
		</div>
	);
}
