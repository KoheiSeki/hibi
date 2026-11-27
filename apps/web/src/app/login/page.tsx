import { AuthFrame } from "@/components/auth/auth-frame";
import { LoginForm } from "./login-form";

type LoginPageProps = {
	searchParams: Promise<{ error?: string }>;
};

export default async function LoginPage({ searchParams }: LoginPageProps) {
	const { error } = await searchParams;
	const showInvalidCredentials = error === "invalid-credentials";

	return (
		<AuthFrame
			title="ログイン"
			description="メールアドレスとパスワードでサインインします。"
		>
			{showInvalidCredentials ? (
				<p className="mb-4 text-sm leading-6 text-destructive" role="alert">
					メールアドレスまたはパスワードが正しくありません。入力内容を確認して、もう一度お試しください。
				</p>
			) : null}
			<LoginForm />
		</AuthFrame>
	);
}
