import { redirect } from "next/navigation";
import { verifySession } from "@/lib/dal";

export default async function RootPage() {
  const session = await verifySession();
  redirect(session ? "/workspaces" : "/login");
}
