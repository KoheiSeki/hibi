import "server-only";

import { type User } from "@supabase/supabase-js";
import { redirect } from "next/navigation";
import { createClient } from "./server";

export async function requireUser(): Promise<User> {
	const supabase = await createClient();
	const {
		data: { user },
	} = await supabase.auth.getUser();
	if (!user) {
		redirect("/login");
	}

	return user;
}
