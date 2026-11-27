import type { ReactNode } from "react";

/**
 * 今日やることが無いときの、糸の最初の節。
 *
 * `CaptureEmptyState` と同じ、苔の点を使った見た目にする。
 */
export function TodayEmptyState(): ReactNode {
	return (
		<div className="flex min-h-40 items-center px-2">
			<div className="grid grid-cols-[1.15rem_minmax(0,1fr)] items-start gap-3">
				<span
					aria-hidden="true"
					className="mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF]"
				/>
				<div>
					<p className="text-base font-semibold text-[#15201A]">
						今日やることはありません
					</p>
					<p className="mt-2 text-sm leading-6 text-[#5A6A62]">
						記録した買い物や予定が、ここに並びます。
					</p>
				</div>
			</div>
		</div>
	);
}
