"use server";

import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { requireSession } from "@/lib/dal";
import { authedJson, authedBackendFetch, ApiError } from "@/lib/backend";
import type { Workspace, Repository } from "@/lib/types";

export interface FormActionState {
  error?: string;
}

export async function createWorkspaceAction(
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const name = String(formData.get("name") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim();
  if (!name) return { error: "Name is required." };

  const session = await requireSession();
  let workspace: Workspace;
  try {
    workspace = await authedJson<Workspace>("/workspaces", session.accessToken, {
      method: "POST",
      body: JSON.stringify({ name, description: description || null }),
    });
  } catch (err) {
    return { error: err instanceof ApiError ? err.message : "Failed to create workspace." };
  }
  revalidatePath("/workspaces");
  redirect(`/workspaces/${workspace.id}`);
}

export async function createRepositoryAction(
  workspaceId: string,
  _prevState: FormActionState,
  formData: FormData,
): Promise<FormActionState> {
  const gitUrl = String(formData.get("git_url") ?? "").trim();
  if (!gitUrl) return { error: "A Git URL is required." };

  const session = await requireSession();
  try {
    await authedJson<Repository>(`/workspaces/${workspaceId}/repositories`, session.accessToken, {
      method: "POST",
      body: JSON.stringify({ git_url: gitUrl }),
    });
  } catch (err) {
    return { error: err instanceof ApiError ? err.message : "Failed to register repository." };
  }
  revalidatePath(`/workspaces/${workspaceId}`);
  return {};
}

export async function deleteRepositoryAction(workspaceId: string, repositoryId: string): Promise<void> {
  const session = await requireSession();
  const res = await authedBackendFetch(
    `/workspaces/${workspaceId}/repositories/${repositoryId}`,
    session.accessToken,
    { method: "DELETE" },
  );
  if (!res.ok && res.status !== 404) {
    throw new Error(`Failed to delete repository (status ${res.status})`);
  }
  revalidatePath(`/workspaces/${workspaceId}`);
  redirect(`/workspaces/${workspaceId}`);
}
