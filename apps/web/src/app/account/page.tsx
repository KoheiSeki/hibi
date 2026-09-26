import { redirect } from "next/navigation";
import { ApiErrorMessage } from "@/components/ui/api-error-message";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getCurrentUserFromApi } from "@/lib/api/server";
import { AccountCard } from "@/components/ui/account-card";
import { createClient } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();
	if (!user) {
		redirect("/login");
	}

	const result = await getCurrentUserFromApi();

	if (!result.ok) {
		if (result.error.kind === "unauthenticated") {
			redirect("/login");
		}

		return (
			<AccountCard>
				<CardContent>
					<ApiErrorMessage error={result.error} />
				</CardContent>
			</AccountCard>
		);
	}

	return (
		<AccountCard>
			<CardHeader>
				<CardTitle>アカウント</CardTitle>
				<p>{user.email}</p>
			</CardHeader>
			<CardContent>
				<p>
					<span className="text-muted-foreground">Supabase user ID:</span>
					<span className="font-mono">{user.id}</span>
				</p>
				<p>
					<span className="text-muted-foreground">API user ID:</span>
					<span className="font-mono">{result.data.userId}</span>
				</p>
			</CardContent>
		</AccountCard>
	);
}
