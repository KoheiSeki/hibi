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
				/>
			</div>
			<FormSubmitButton pendingLabel="ログイン中…">ログイン</FormSubmitButton>
		</form>
	);
}
