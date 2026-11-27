import type { ActionState } from "@/lib/action-state";
import type { DigestReportResponse } from "@hibi/api-client";

/** ダイジェストをもう一度作る操作の結果。成功すると、pending に戻ったレポートを持つ。 */
export type RetryDigestReportActionState = ActionState<DigestReportResponse>;

/** いちばん新しいダイジェストを読んだ結果。レポートがまだなければ、`data` は `null`。 */
export type GetLatestDigestReportActionState =
	ActionState<DigestReportResponse | null>;
