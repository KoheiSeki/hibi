import { signOutAction } from "@/app/account/actions";
import { Card, CardFooter } from "./card";
import { FormSubmitButton } from "./form-submit-button";

export function AccountCard({ children }: { children: React.ReactNode }) {
	return (
		<Card>
			{children}
			<CardFooter>
				<form action={signOutAction}>
					<FormSubmitButton
						variant="outline"
						pendingLabel="ログアウト中…"
					>
						ログアウト
					</FormSubmitButton>
				</form>
			</CardFooter>
		</Card>
	);
}
