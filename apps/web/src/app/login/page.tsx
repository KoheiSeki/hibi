import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { signInAction } from "./actions";

export default function LoginPage() {
	return (
		<Card>
			<CardHeader>
				<CardTitle>ログイン</CardTitle>
				<CardDescription>
					メールアドレスとパスワードでサインインします。
				</CardDescription>
			</CardHeader>
			<CardContent>
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
					<Button type="submit">ログイン</Button>
				</form>
			</CardContent>
		</Card>
	);
}
