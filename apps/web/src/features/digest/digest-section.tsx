import "server-only";

import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { listDigestReportsFromApi } from "@/lib/api/digest";

import { DigestEmptyState } from "./digest-empty-state";
import { DigestReportCard } from "./digest-report-card";

/**
 * 最新の朝のダイジェストと週次レビューを API から読み、並べて出す。
 *
 * 種類ごとに 1 件ずつ、2 回に分けて読む。1 回の一覧では、毎日できる daily に押されて、
 * 最大 13 日前に始まる weekly が入らないことがある。どちらかが失敗したら、未認証は
 * ログインへ移り、それ以外はエラーメッセージを出す。両方とも無ければ空状態を出す。
 * カードには、id と状態を並べた `key` を付ける。もう一度作ったあとにサーバー側の
 * データが変わると、カードの state が作り直される。
 */
export async function DigestSection(): Promise<ReactNode> {
	const [dailyResult, weeklyResult] = await Promise.all([
		listDigestReportsFromApi({ kind: "daily", limit: 1 }),
		listDigestReportsFromApi({ kind: "weekly", limit: 1 }),
	]);

	for (const result of [dailyResult, weeklyResult]) {
		if (!result.ok) {
			if (result.error.kind === "unauthenticated") {
				redirect("/login");
			}

			return <ApiErrorMessage error={result.error} />;
		}
	}

	const reports = [dailyResult, weeklyResult].flatMap((result) =>
		result.ok ? result.data.slice(0, 1) : [],
	);
	if (reports.length === 0) {
		return <DigestEmptyState />;
	}

	return (
		<div className="divide-y divide-[#D5E3D9]">
			{reports.map((report) => (
				<div key={report.kind} className="py-7 first:pt-2">
					<DigestReportCard
						key={`${report.id}:${report.status}`}
						report={report}
					/>
				</div>
			))}
		</div>
	);
}
