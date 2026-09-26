import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { LoginForm } from "./login-form";

type LoginPageProps = {
	searchParams: Promise<{ error?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
	const { error } = await searchParams;
	const showInvalidCredentials = error === "invalid-credentials";

	return (
		<Card>
			<CardHeader>
				<CardTitle>ログイン</CardTitle>
				<CardDescription>
					メールアドレスとパスワードでサインインします。
				</CardDescription>
			</CardHeader>
			<CardContent className="flex flex-col gap-4">
				{showInvalidCredentials ? (
					<Alert variant="destructive">
						<AlertTitle>ログインできませんでした</AlertTitle>
						<AlertDescription>
							<p>
								メールアドレスまたはパスワードが正しくありません。入力内容を確認して、もう一度お試しください。
							</p>
						</AlertDescription>
					</Alert>
				) : null}
				<LoginForm />
			</CardContent>
		</Card>
	);
}
