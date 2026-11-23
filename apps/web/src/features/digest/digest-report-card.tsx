"use client";

import type { DigestReportResponse } from "@hibi/api-client";
import Link from "next/link";
import { type ReactNode, useState, useTransition } from "react";

import { Button } from "@/components/ui/button";
import { formatJstDueLabel } from "@/lib/date-time";

import { retryDigestReportAction } from "./actions";
import {
	type DailyDigestContent,
	type WeeklyReviewContent,
	formatPeriodStart,
	parseDailyDigestContent,
	parseWeeklyReviewContent,
} from "./digest-content";
import { useDigestPolling } from "./use-digest-polling";

const GENERATION_FAILED_MESSAGE = "作れませんでした。";

const FAILURE_MESSAGES: Readonly<Record<string, string>> = {
	generation_failed: GENERATION_FAILED_MESSAGE,
	review_provider_error: "要約のサービスにつながらず、作れませんでした。",
};

/**
 * `errorCode` を、利用者に見せる一言にする。
 *
 * API に新しい理由が足されても画面が壊れないよう、知らない値は
 * `generation_failed` と同じ文にする。
 */
function failureMessage(errorCode: string | null | undefined): string {
	return (
		(errorCode ? FAILURE_MESSAGES[errorCode] : undefined) ??
		GENERATION_FAILED_MESSAGE
	);
}

type DigestReportCardProps = {
	report: DigestReportResponse;
};

/**
 * 朝のダイジェストか週次レビューを 1 件、状態に合わせて出す。
 *
 * ready は中身を、pending は「作っています」を出し、3 秒おきに読み直す。failed は
 * 理由の一言と「もう一度作る」を出す。もう一度作るのに成功したら、返った pending の
 * 行に替えて読み直しを始める。失敗したときはボタンを残し、理由を alert に出す。
 * サーバー側のデータが変わったときは、呼び出し側が `key` を変えて、この state を作り直す。
 *
 * @param props.report - 表示するレポート
 */
export function DigestReportCard({
	report: initialReport,
}: DigestReportCardProps) {
	const [report, setReport] = useState(initialReport);
	const [retryError, setRetryError] = useState<string | null>(null);
	const [retrying, startTransition] = useTransition();
	const { error: pollingError } = useDigestPolling({
		report,
		onReport: setReport,
	});
	const error = retryError ?? pollingError;
	const isDaily = report.kind === "daily";
	const periodLabel = isDaily
		? formatPeriodStart(report.periodStart)
		: `${formatPeriodStart(report.periodStart)}からの一週間`;

	function handleRetry() {
		if (retrying) {
			return;
		}

		setRetryError(null);
		startTransition(async () => {
			const result = await retryDigestReportAction(report.id);
			if (result.status === "error") {
				setRetryError(result.message);
				return;
			}
			if (result.status === "success") {
				setReport(result.data);
			}
		});
	}

	return (
		<section aria-labelledby={`digest-${report.id}`}>
			<header className="grid grid-cols-[1.15rem_minmax(0,1fr)] items-baseline gap-3">
				<span
					aria-hidden="true"
					className="size-3 translate-y-0.5 justify-self-center rounded-full border-2 border-[#1E6B43] bg-[#EEF3EF]"
				/>
				<div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
					<h2
						id={`digest-${report.id}`}
						className="text-[1.3rem] font-medium leading-tight tracking-[0.04em] text-[#15201A] [font-family:var(--font-capture-display),serif]"
					>
						{isDaily ? "朝のダイジェスト" : "週次レビュー"}
					</h2>
					<time
						dateTime={report.periodStart}
						className="text-sm tabular-nums text-[#5A6A62]"
					>
						{periodLabel}
					</time>
				</div>
			</header>

			<div className="mt-3 pl-[calc(1.15rem+0.75rem)]">
				{report.status === "ready" ? (
					isDaily ? (
						<DailyDigestBody
							content={parseDailyDigestContent(report.content)}
						/>
					) : (
						<WeeklyReviewBody
							content={parseWeeklyReviewContent(report.content)}
						/>
					)
				) : null}

				{report.status === "pending" ? (
					<div className="py-2">
						<p className="text-base text-[#15201A]">作っています</p>
						<p className="mt-1 text-sm leading-6 text-[#5A6A62]">
							できあがると、ここに出ます。
						</p>
					</div>
				) : null}

				{report.status === "failed" ? (
					<div className="flex flex-wrap items-center justify-between gap-3 py-2">
						<p className="text-base text-[#15201A]">
							{failureMessage(report.errorCode)}
						</p>
						<Button
							type="button"
							variant="ghost"
							onClick={handleRetry}
							disabled={retrying}
							className="h-8 rounded-full px-3 text-sm text-[#1E6B43] hover:bg-[#F7FBF8] hover:text-[#1E6B43]"
						>
							{retrying ? "頼んでいます" : "もう一度作る"}
						</Button>
					</div>
				) : null}

				{error ? (
					<p className="mt-2 text-sm text-destructive" role="alert">
						{error}
					</p>
				) : null}
			</div>
		</section>
	);
}

/** 形を読めなかった中身の代わりに出す一言。 */
function UnreadableContent(): ReactNode {
	return (
		<p className="py-2 text-sm text-[#5A6A62]">中身を表示できませんでした。</p>
	);
}

/**
 * 朝のダイジェストの件数と、今日やることの上位を、糸と節で出す。
 *
 * 件数は 1 行の文にして、数字を飾らない。緊急度の色分けはしない(仕様)。
 */
function DailyDigestBody({
	content,
}: {
	content: DailyDigestContent | null;
}): ReactNode {
	if (content === null) {
		return <UnreadableContent />;
	}

	const { items } = content;

	return (
		<div>
			<p className="flex flex-wrap gap-x-4 gap-y-1 text-sm leading-6 text-[#5A6A62]">
				<span>{`期限が過ぎた ${content.overdueCount} 件`}</span>
				<span>{`今日が期限 ${content.dueTodayCount} 件`}</span>
				<span>{`昨日 ${content.doneYesterdayCount} 件完了`}</span>
			</p>

			{items.length === 0 ? (
				<p className="mt-3 text-sm leading-6 text-[#5A6A62]">
					今日やることはありません。
				</p>
			) : (
				<ul
					className="relative mt-2 -ml-[calc(1.15rem+0.75rem)]"
					aria-label="今日やることの上位"
				>
					{items.map((item, index) => {
						const threadClass =
							items.length === 1
								? "hidden"
								: index === 0
									? "top-6 bottom-0"
									: index === items.length - 1
										? "top-0 h-6"
										: "top-0 bottom-0";
						return (
							<li key={item.captureId} className="relative">
								<span
									aria-hidden="true"
									className={`absolute left-[0.53rem] w-px bg-[#D5E3D9] ${threadClass}`}
								/>
								<Link
									href={`/captures/${item.captureId}`}
									className="group grid grid-cols-[1.15rem_4.6rem_minmax(0,1fr)] items-start gap-3 py-3 text-[#15201A] no-underline outline-none"
								>
									<span
										aria-hidden="true"
										className="relative z-10 mt-1.5 size-2 justify-self-center rounded-full bg-[#1E6B43] ring-4 ring-[#EEF3EF] transition-transform group-hover:scale-125 motion-reduce:transition-none"
									/>
									{item.dueAt ? (
										<time
											dateTime={item.dueAt}
											className="pt-0.5 text-sm font-medium tabular-nums text-[#5A6A62]"
										>
											{formatJstDueLabel(item.dueAt)}
										</time>
									) : (
										<span className="pt-0.5 text-sm text-[#5A6A62]">
											期限なし
										</span>
									)}
									<span className="line-clamp-2 text-[1.0625rem] leading-7 group-hover:text-[#1E6B43] group-focus-visible:rounded-md group-focus-visible:ring-2 group-focus-visible:ring-[#1E6B43]">
										{item.title}
									</span>
								</Link>
							</li>
						);
					})}
				</ul>
			)}
		</div>
	);
}

/**
 * 週次レビューの要約と集計を出す。
 *
 * 要約は読み物なので、見出しと同じ明朝で、行間を広めに組む。集計は、その下に
 * 静かな 1 行で添える。
 */
function WeeklyReviewBody({
	content,
}: {
	content: WeeklyReviewContent | null;
}): ReactNode {
	if (content === null) {
		return <UnreadableContent />;
	}

	const { stats } = content;

	return (
		<div className="py-1">
			<p className="max-w-[34em] text-[1.0625rem] leading-8 text-[#15201A] [font-family:var(--font-capture-display),serif]">
				{content.summary}
			</p>
			<ul
				className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm leading-6 text-[#5A6A62]"
				aria-label="先週の集計"
			>
				<li>{`記録 ${stats.capturedCount} 件`}</li>
				<li>{`完了 ${stats.doneCount} 件`}</li>
				<li>{`未完了 ${stats.openCount} 件`}</li>
				<li>{`期限超過 ${stats.overdueCount} 件`}</li>
			</ul>
		</div>
	);
}
