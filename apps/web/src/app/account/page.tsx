import { redirect } from "next/navigation";
import { createClient } from "@/lib/auth/server";
import { signOutAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function AccountPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");
  return (
    <section className="card">
      <h1>アカウント</h1>
      <p>{user.email}</p>
      <form action={signOutAction}>
        <button type="submit">ログアウト</button>
      </form>
    </section>
  );
}
