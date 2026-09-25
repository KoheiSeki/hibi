import { redirect } from "next/navigation";
import { AccountCard } from "@/components/ui/account-card";
import { CardHeader, CardTitle } from "@/components/ui/card";
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

	return (
		<AccountCard>
			<CardHeader>
				<CardTitle>アカウント</CardTitle>
				<p>{user.email}</p>
			</CardHeader>
		</AccountCard>
	);
}
