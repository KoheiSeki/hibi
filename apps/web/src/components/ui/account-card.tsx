import { signOutAction } from "@/app/account/actions";
import { Button } from "./button";
import { Card, CardFooter } from "./card";

export function AccountCard({ children }: { children: React.ReactNode }) {
	return (
		<Card>
			{children}
			<CardFooter>
				<form action={signOutAction}>
					<Button type="submit" variant="outline">
						ログアウト
					</Button>
				</form>
			</CardFooter>
		</Card>
	);
}
