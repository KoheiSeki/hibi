"use client";

import type { ComponentProps, ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

type CaptureComposerViewProps = Omit<ComponentProps<"form">, "children"> & {
	defaultValue?: string;
	fieldError?: string;
	message?: ReactNode;
	pending?: boolean;
	submitDisabled?: boolean;
};
export function CaptureComposerView({
	className,
	defaultValue,
	fieldError,
	message,
	pending = false,
	submitDisabled = false,
	...formProps
}: CaptureComposerViewProps) {
	const errorId = fieldError ? "capture-raw-text-error" : undefined;

	return (
		<form
			className={cn(
				"grid gap-2.5 rounded-[1.4rem] border border-[#D5E3D9] bg-[#F7FBF8] p-3 shadow-[0_16px_40px_rgb(21_32_26/0.08)]",
				className,
			)}
			aria-label="新しい記録"
			{...formProps}
		>
			<Label htmlFor="capture-raw-text" className="sr-only">
				何を残しますか
			</Label>
			<Textarea
				id="capture-raw-text"
				name="rawText"
				defaultValue={defaultValue}
				placeholder="何を残しますか"
				maxLength={2000}
				rows={2}
				aria-describedby={errorId}
				aria-invalid={fieldError ? true : undefined}
				className="min-h-20 resize-none rounded-2xl border-[#D5E3D9] bg-white px-4 py-3 text-[1.0625rem] leading-7 text-[#15201A] placeholder:text-[#5A6A62] focus-visible:border-[#1E6B43] focus-visible:ring-[#1E6B43]/20"
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

			{message ? <div className="text-sm text-[#5A6A62]">{message}</div> : null}

			<Button
				type="submit"
				disabled={pending || submitDisabled}
				className="h-11 w-full rounded-2xl bg-[#1E6B43] font-sans text-base font-semibold text-white shadow-[0_8px_18px_rgb(30_107_67/0.22)] hover:bg-[#185838] focus-visible:border-[#144C30] focus-visible:ring-[#1E6B43]/30"
			>
				{pending ? "記録しています" : "記録する"}
			</Button>
		</form>
	);
}
