import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
	Card,
	CardContent,
	CardDescription,
	CardHeader,
	CardTitle,
} from "@/components/ui/card";
import { createClient } from "@/lib/auth/server";
import { redirect } from "next/navigation";

export default async function HomePage() {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();

	if (user) {
		redirect("/captures");
	}

	return (
		<Card>
			<CardHeader>
				<CardDescription>毎日を、少し軽やかに。</CardDescription>
				<CardTitle className="text-2xl">Hibi</CardTitle>
			</CardHeader>
			<CardContent className="flex flex-col gap-4">
				<p className="text-muted-foreground">
					日々の入力を整理するコパイロットの基盤です。
				</p>
				<Button asChild>
					<Link href="/login">ログイン</Link>
				</Button>
			</CardContent>
		</Card>
	);
}
