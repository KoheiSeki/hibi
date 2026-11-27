import "server-only";

import type { ReactNode } from "react";
import { redirect } from "next/navigation";

import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { listTodayCapturesFromApi } from "@/lib/api/capture";

import { TodayEmptyState } from "./today-empty-state";
import { TodayList } from "./today-list";

/**
 * 今日やることを API から取得し、結果に合わせて表示を出し分ける。
 *
 * 未認証ならログインへ移る。それ以外の失敗は、エラーメッセージを出す。0 件なら
 * 空状態を出す。一覧には、記録の id を並べた `key` を付ける。完了にしたあとに
 * サーバー側のデータが変わると、`TodayList` の state が作り直される。
 */
export async function TodaySection(): Promise<ReactNode> {
	const result = await listTodayCapturesFromApi();
	if (!result.ok) {
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		return <ApiErrorMessage error={result.error} />;
	}

	const captures = result.data;
	if (captures.length === 0) {
		return <TodayEmptyState />;
	}

	return (
		<TodayList key={captures.map(({ id }) => id).join(":")} items={captures} />
	);
}
