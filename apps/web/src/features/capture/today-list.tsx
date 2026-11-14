"use client";

import type { CaptureResponse } from "@hibi/api-client";
import Link from "next/link";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { formatJstTime } from "@/lib/date-time";

import { markScenarioDoneAction } from "./actions";
import { TodayEmptyState } from "./today-empty-state";

type TodayListProps = {
	items: readonly CaptureResponse[];
};

/**
 * 今日やることを、糸と節の一覧で出し、行ごとに完了にできるようにする。
 *
 * 完了にした行は、API が成功を返したあとに一覧から外す。失敗したときは行を残し、
 * 一覧の下にエラーを出す。サーバー側のデータが変わったときは、呼び出し側が
 * `key` を変えて、この state を作り直す。
 *
 * @param props.items - 優先度の高い順の記録。シナリオを含む。
 */
export function TodayList({ items: initialItems }: TodayListProps) {
	const [items, setItems] = useState<readonly CaptureResponse[]>(initialItems);
	const [error, setError] = useState<string | null>(null);
	const [pendingId, setPendingId] = useState<string | null>(null);
	const [pending, startTransition] = useTransition();

	function handleDone(captureId: string) {
		if (pending) {
			return;
		}

		setError(null);
		setPendingId(captureId);
		startTransition(async () => {
			const result = await markScenarioDoneAction(captureId);
			setPendingId(null);
			if (result.status === "error") {
				setError(result.message);
				return;
			}
			setItems((current) => current.filter(({ id }) => id !== captureId));
		});
	}

	if (items.length === 0) {
		return <TodayEmptyState />;
	}

	return (
		<div>
			<ul className="relative" aria-label="今日やること">
				{items.map((item) => {
					const dueAt = item.scenario?.dueAt;
					return (
						<li key={item.id} className="relative">
							<span
								aria-hidden="true"
								className="absolute bottom-0 left-[0.42rem] top-0 w-px bg-[#D5E3D9]"
							/>
							<div className="grid min-h-16 grid-cols-[minmax(0,1fr)_auto] items-start gap-3 py-4">
								<Link
									href={`/captures/${item.id}`}
									className="group grid grid-cols-[1.15rem_3.4rem_minmax(0,1fr)] items-start gap-3 text-[#15201A] no-underline outline-none"
								>
									<span
										aria-hidden="true"
										className="relative z-10 mt-1.5 size-2.5 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF] transition-transform group-hover:scale-125"
									/>
									{dueAt ? (
										<time
											dateTime={dueAt}
											className="pt-0.5 text-sm font-medium tabular-nums text-[#5A6A62]"
										>
											{formatJstTime(dueAt)}
										</time>
									) : (
										<span aria-hidden="true" />
									)}
									<span className="line-clamp-2 text-[1.0625rem] leading-7 group-hover:text-[#1E6B43] group-focus-visible:rounded-md group-focus-visible:ring-2 group-focus-visible:ring-[#1E6B43]">
										{item.scenario?.title ?? item.rawText}
									</span>
								</Link>
								<Button
									type="button"
									variant="outline"
									onClick={() => handleDone(item.id)}
									disabled={pending}
									className="h-9 rounded-full border-[#D5E3D9] bg-[#F7FBF8] px-4 text-sm text-[#1E6B43]"
								>
									{pendingId === item.id ? "完了しています" : "完了にする"}
								</Button>
							</div>
						</li>
					);
				})}
			</ul>

			{error ? (
				<p className="mt-4 text-center text-sm text-destructive" role="alert">
					{error}
				</p>
			) : null}
		</div>
	);
}
