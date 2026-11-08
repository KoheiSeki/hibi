import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { CaptureSearchMode } from "@/lib/api/capture-search";

import { CAPTURE_SEARCH_MAX_LENGTH } from "./capture-search-params";

type CaptureSearchFormProps = {
	defaultQuery: string;
	defaultMode: CaptureSearchMode;
};

const MODE_OPTIONS: readonly { value: CaptureSearchMode; label: string }[] = [
	{ value: "keyword", label: "キーワード" },
	{ value: "semantic", label: "意味" },
];

/**
 * 記録の検索欄。GET で `/captures?q=&mode=` へ遷移するだけで、状態は持たない。
 *
 * @param props.defaultQuery - 入力欄の初期値。検索中は現在の検索語。
 * @param props.defaultMode - 選択済みにする検索方法。
 */
export function CaptureSearchForm({
	defaultQuery,
	defaultMode,
}: CaptureSearchFormProps): ReactNode {
	return (
		<form
			role="search"
			method="get"
			action="/captures"
			className="grid gap-2.5 pb-3"
		>
			<div className="flex gap-2">
				<Input
					type="search"
					name="q"
					defaultValue={defaultQuery}
					maxLength={CAPTURE_SEARCH_MAX_LENGTH}
					aria-label="記録を検索"
					placeholder="記録を検索"
					className="h-11 rounded-full border-[#D5E3D9] bg-[#F7FBF8] px-4 text-[1.0625rem] text-[#15201A] placeholder:text-[#5A6A62] focus-visible:border-[#1E6B43] focus-visible:ring-[#1E6B43]/20"
				/>
				<Button
					type="submit"
					className="h-11 rounded-full bg-[#1E6B43] px-5 text-white hover:bg-[#1E6B43]/90"
				>
					検索
				</Button>
			</div>
			<fieldset className="flex gap-4 border-0 p-0">
				<legend className="sr-only">検索方法</legend>
				{MODE_OPTIONS.map(({ value, label }) => (
					<label
						key={value}
						className="flex items-center gap-1.5 text-sm text-[#5A6A62]"
					>
						<input
							type="radio"
							name="mode"
							value={value}
							defaultChecked={value === defaultMode}
							className="accent-[#1E6B43]"
						/>
						{label}
					</label>
				))}
			</fieldset>
		</form>
	);
}
