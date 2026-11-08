import { CaptureSearch } from "@/lib/api/capture-search";

/** API の `q` の上限。サーバー側の検証(200 文字)と同じ値。 */
export const CAPTURE_SEARCH_MAX_LENGTH = 200;

/**
 * page の searchParams を、検索 API に渡せる形へ正規化する。
 *
 * 値が配列(`?q=a&q=b`)なら先頭を使う。`q` は前後の空白を除き、
 * 1 文字以上 CAPTURE_SEARCH_MAX_LENGTH 文字以下のときだけ有効とする。
 * `mode` は `"semantic"` のときだけ semantic、それ以外は keyword に倒す。
 * 不正な入力でも例外にはしない。
 *
 * @param params - `await searchParams` の結果。URL の生の値。
 * @returns 検索すべきなら `{ q, mode }`。`q` が無い、空白だけ、
 *   または長すぎるときは `null`(呼び出し側は通常の一覧を出す)。
 */
export function parseCaptureSearchParams(
	params: Record<string, string | string[] | undefined>,
): CaptureSearch | null {
	const q = firstValue(params.q)?.trim();
	if (
		q === undefined ||
		q.length === 0 ||
		q.length > CAPTURE_SEARCH_MAX_LENGTH
	) {
		return null;
	}
	const mode = firstValue(params.mode) === "semantic" ? "semantic" : "keyword";
	return { q, mode };
}

function firstValue(value: string | string[] | undefined): string | undefined {
	return Array.isArray(value) ? value[0] : value;
}
