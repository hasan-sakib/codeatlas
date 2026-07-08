"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireSession } from "@/lib/dal";
import { authedJson, authedBackendFetch } from "@/lib/backend";
import type { Conversation } from "@/lib/types";

export async function createConversationAction(workspaceId: string): Promise<void> {
  const session = await requireSession();
  const conversation = await authedJson<Conversation>(
    `/workspaces/${workspaceId}/conversations`,
    session.accessToken,
    { method: "POST", body: JSON.stringify({}) },
  );
  redirect(`/workspaces/${workspaceId}/conversations/${conversation.id}`);
}

export async function deleteConversationAction(workspaceId: string, conversationId: string): Promise<void> {
  const session = await requireSession();
  const res = await authedBackendFetch(
    `/workspaces/${workspaceId}/conversations/${conversationId}`,
    session.accessToken,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete conversation (status ${res.status})`);
  }
  revalidatePath(`/workspaces/${workspaceId}/conversations`);
  redirect(`/workspaces/${workspaceId}/conversations`);
}
