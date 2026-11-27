import { type ReactNode, Suspense } from "react";

import { CaptureListSkeleton } from "@/features/capture/capture-list-skeleton";
import { DigestSection } from "@/features/digest/digest-section";
import { requireUser } from "@/lib/auth/require-user";

/**
 * 朝のダイジェストと週次レビューの画面。
 *
 * 認証済みのユーザーだけが開ける。取得を待つあいだは、記録の一覧と同じ
 * スケルトンを出す。
 */
export default async function DigestPage(): Promise<ReactNode> {
	await requireUser();

	return (
		<section className="mx-auto w-full max-w-2xl px-5 pb-32 pt-7 sm:px-8">
			<h1 className="pb-4 text-[1.65rem] font-medium leading-none tracking-[0.04em] text-[#15201A] [font-family:var(--font-capture-display),serif]">
				ダイジェスト
			</h1>
			<Suspense fallback={<CaptureListSkeleton />}>
				<DigestSection />
			</Suspense>
		</section>
	);
}
