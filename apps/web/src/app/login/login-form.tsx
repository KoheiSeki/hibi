"use client";

import { FormSubmitButton } from "@/components/ui/form-submit-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signInAction } from "./actions";

export function LoginForm() {
	return (
		<form action={signInAction} className="flex flex-col gap-4">
			<div className="grid gap-2">
				<Label htmlFor="email">メール</Label>
				<Input
					id="email"
					name="email"
					type="email"
					autoComplete="email"
					required
					className="h-11 rounded-xl border-[#D5E3D9] bg-white text-[#15201A] focus-visible:border-[#1E6B43] focus-visible:ring-[#1E6B43]/20"
				/>
			</div>
			<div className="grid gap-2">
				<Label htmlFor="password">パスワード</Label>
				<Input
					id="password"
					name="password"
					type="password"
					autoComplete="current-password"
					required
					className="h-11 rounded-xl border-[#D5E3D9] bg-white text-[#15201A] focus-visible:border-[#1E6B43] focus-visible:ring-[#1E6B43]/20"
				/>
			</div>
			<FormSubmitButton
				pendingLabel="ログイン中…"
				className="h-11 rounded-2xl bg-[#1E6B43] text-base font-semibold text-white shadow-[0_8px_18px_rgb(30_107_67/0.22)] hover:bg-[#185838]"
			>
				ログイン
			</FormSubmitButton>
		</form>
	);
}
