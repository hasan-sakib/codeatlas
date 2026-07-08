"use server";

import { redirect } from "next/navigation";
import * as backend from "@/lib/backend";
import { createSession, deleteSession } from "@/lib/session";
import { verifySession } from "@/lib/dal";
import { ApiError } from "@/lib/api-errors";

export interface AuthFormState {
  error?: string;
}

export async function loginAction(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  let redirectTo = "/workspaces";
  try {
    const tokens = await backend.login(email, password);
    const user = await backend.fetchCurrentUser(tokens.access_token);
    await createSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      userId: user.id,
      email: user.email,
      accessTokenExpiresAt: backend.accessTokenExpiryMs(tokens.access_token),
    });
    const next = formData.get("next");
    if (typeof next === "string" && next.startsWith("/")) {
      redirectTo = next;
    }
  } catch (err) {
    if (err instanceof ApiError) {
      return { error: err.status === 401 ? "Invalid email or password." : err.message };
    }
    return { error: "Something went wrong. Please try again." };
  }
  redirect(redirectTo);
}

export async function registerAction(
  _prevState: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const fullName = String(formData.get("full_name") ?? "");
  if (!email || !password) {
    return { error: "Email and password are required." };
  }

  try {
    await backend.register(email, password, fullName || undefined);
    const tokens = await backend.login(email, password);
    const user = await backend.fetchCurrentUser(tokens.access_token);
    await createSession({
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      userId: user.id,
      email: user.email,
      accessTokenExpiresAt: backend.accessTokenExpiryMs(tokens.access_token),
    });
  } catch (err) {
    if (err instanceof ApiError) {
      return { error: err.status === 409 ? "An account with that email already exists." : err.message };
    }
    return { error: "Something went wrong. Please try again." };
  }
  redirect("/workspaces");
}

export async function logoutAction(): Promise<void> {
  const session = await verifySession();
  if (session) {
    try {
      await backend.logout(session.accessToken, session.refreshToken);
    } catch {
      // Best-effort — the cookie is deleted regardless, so the user is
      // logged out client-side even if the backend call fails.
    }
  }
  await deleteSession();
  redirect("/login");
}
