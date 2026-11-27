import type { ReactNode } from "react";

import { signOutAction } from "@/app/account/actions";

import { AuthFrame } from "../auth/auth-frame";
import { FormSubmitButton } from "./form-submit-button";

export function AccountCard({ children }: { children: ReactNode }) {
	return (
		<AuthFrame title="アカウント" description="このブラウザのログインを終了できます。">
			<div className="flex flex-col gap-4 text-sm leading-6">{children}</div>
			<form action={signOutAction} className="mt-6">
				<FormSubmitButton
					variant="outline"
					pendingLabel="ログアウト中…"
					className="h-11 rounded-2xl border-[#D5E3D9] bg-white text-[#15201A] hover:border-[#1E6B43] hover:text-[#1E6B43]"
				>
					ログアウト
				</FormSubmitButton>
			</form>
		</AuthFrame>
	);
}
