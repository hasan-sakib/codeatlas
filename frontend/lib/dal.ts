import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import {
  createSession,
  decryptSession,
  deleteSession,
  readSessionCookie,
  type SessionPayload,
} from "@/lib/session";
import { refresh as refreshBackend, accessTokenExpiryMs } from "@/lib/backend";

const REFRESH_SKEW_MS = 30_000;

/** The real (not merely optimistic) authorization boundary — see
 * proxy.ts for the optimistic redirect layer. `cache()`-wrapped so every
 * Server Component/Action/Route Handler in a single request shares one
 * decrypt + (at most one) refresh call rather than repeating it. */
export const verifySession = cache(async (): Promise<SessionPayload | null> => {
  const cookieValue = await readSessionCookie();
  if (!cookieValue) return null;

  const payload = await decryptSession(cookieValue);
  if (!payload) return null;

  if (Date.now() < payload.accessTokenExpiresAt - REFRESH_SKEW_MS) {
    return payload;
  }

  // Access token is expired or about to be — rotate it. The backend
  // rotates the refresh token on every use, so the old one becomes
  // invalid the instant this succeeds; the new session cookie must be
  // written immediately or the next request would present a
  // now-revoked refresh token.
  try {
    const tokens = await refreshBackend(payload.refreshToken);
    const rotated: SessionPayload = {
      ...payload,
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      accessTokenExpiresAt: accessTokenExpiryMs(tokens.access_token),
    };
    await createSession(rotated);
    return rotated;
  } catch {
    await deleteSession();
    return null;
  }
});

/** For Server Components/Actions that require an authenticated caller —
 * redirects rather than returning null, so call sites don't need their
 * own not-authenticated branch. */
export async function requireSession(): Promise<SessionPayload> {
  const session = await verifySession();
  if (!session) {
    redirect("/login");
  }
  return session;
}
