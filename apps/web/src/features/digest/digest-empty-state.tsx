import type { ReactNode } from "react";

/**
 * ダイジェストがまだ 1 件も無いときの、糸の最初の節。
 *
 * `TodayEmptyState` と同じ、苔の点を使った見た目にする。いつできるかを伝え、
 * 待てば何が出るかが分かるようにする。
 */
export function DigestEmptyState(): ReactNode {
	return (
		<div className="flex min-h-40 items-center px-2">
			<div className="grid grid-cols-[1.15rem_minmax(0,1fr)] items-start gap-3">
				<span
					aria-hidden="true"
					className="mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF]"
				/>
				<div>
					<p className="text-base font-semibold text-[#15201A]">
						ダイジェストは毎朝 7 時に作ります
					</p>
					<p className="mt-2 text-sm leading-6 text-[#5A6A62]">
						今日やることの上位と、期限の件数が、ここに並びます。月曜の朝には、先週の振り返りも届きます。
					</p>
				</div>
			</div>
		</div>
	);
}
