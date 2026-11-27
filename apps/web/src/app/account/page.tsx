import { redirect } from "next/navigation";
import { ApiErrorMessage } from "@/components/ui/api-error-message";
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
				<ApiErrorMessage error={result.error} />
			</AccountCard>
		);
	}

	return (
		<AccountCard>
			<p className="text-base text-[#15201A]">{user.email}</p>
			<p>
				<span className="text-[#5A6A62]">ログイン ID:</span>{" "}
				<span className="font-mono text-[#15201A]">{user.id}</span>
			</p>
			<p>
				<span className="text-[#5A6A62]">API ID:</span>{" "}
				<span className="font-mono text-[#15201A]">{result.data.userId}</span>
			</p>
		</AccountCard>
	);
}
