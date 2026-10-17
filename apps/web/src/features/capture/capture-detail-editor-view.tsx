import type { ComponentProps, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type CaptureDetailEditorViewProps = {
	defaultValue: string;
	timeLabel: string;
	fieldError?: string;
	message?: ReactNode;
	errorMessage?: string;
	updateFormProps?: Omit<ComponentProps<"form">, "children">;
	deleteButtonProps?: Omit<ComponentProps<typeof Button>, "children">;
	updatePending?: boolean;
	deletePending?: boolean;
};

export function CaptureDetailEditorView({
	defaultValue,
	timeLabel,
	fieldError,
	message,
	errorMessage,
	updateFormProps,
	deleteButtonProps,
	updatePending = false,
	deletePending = false,
}: CaptureDetailEditorViewProps) {
	const errorId = fieldError ? "capture-detail-raw-text-error" : undefined;
	const deleteErrorId = errorMessage
		? "capture-detail-delete-error"
		: undefined;

	return (
		<article className="px-5 pb-[max(2rem,env(safe-area-inset-bottom))] pt-8 sm:px-8">
			<p className="mb-6 text-[1.35rem] font-medium leading-none tracking-[0.03em] text-[#15201A] tabular-nums [font-family:var(--font-capture-display),serif]">
				{timeLabel}
			</p>

			<form className="grid gap-3" {...updateFormProps}>
				<Label htmlFor="capture-detail-raw-text" className="sr-only">
					記録の本文
				</Label>
				<Textarea
					id="capture-detail-raw-text"
					name="rawText"
					defaultValue={defaultValue}
					maxLength={2000}
					rows={8}
					aria-describedby={errorId}
					aria-invalid={fieldError ? true : undefined}
					className="min-h-56 resize-y rounded-[1.25rem] border-[#D5E3D9] bg-white px-4 py-4 text-[1.0625rem] leading-[1.7] text-[#15201A] shadow-[0_12px_32px_rgb(21_32_26/0.05)] focus-visible:border-[#1E6B43] focus-visible:ring-[#1E6B43]/20"
				/>

				{fieldError ? (
					<p
						id={errorId}
						className="text-sm leading-5 text-destructive"
						role="alert"
					>
						{fieldError}
					</p>
				) : null}

				{message ? (
					<div className="text-sm text-[#5A6A62]">{message}</div>
				) : null}

				<Button
					type="submit"
					disabled={updatePending}
					className="h-11 rounded-2xl bg-[#1E6B43] font-sans text-base font-semibold text-white shadow-[0_8px_18px_rgb(30_107_67/0.22)] hover:bg-[#185838]"
				>
					{updatePending ? "保存しています" : "保存する"}
				</Button>
			</form>

			<div className="mt-10 border-t border-[#D5E3D9] pt-5">
				{errorMessage ? (
					<p
						id={deleteErrorId}
						className="mb-3 text-sm leading-5 text-destructive"
						role="alert"
					>
						{errorMessage}
					</p>
				) : null}
				<Button
					{...deleteButtonProps}
					type="button"
					variant="destructive"
					disabled={deletePending}
					aria-describedby={deleteErrorId}
					className="h-11 w-full rounded-2xl border border-[#E7C8C4] bg-transparent font-sans text-base font-semibold text-[#8A3E36] hover:bg-[#F8EDEC]"
				>
					{deletePending ? "削除しています" : "削除する"}
				</Button>
			</div>
		</article>
	);
}
