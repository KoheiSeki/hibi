"use server";

import { redirect } from "next/navigation";
import { createClient } from "@/lib/auth/server";

export async function signOutAction() {
  const supabase = await createClient();
  const { error } = await supabase.auth.signOut({ scope: "local" });
  if (error) {
    throw error;
  }
  redirect("/login");
}
