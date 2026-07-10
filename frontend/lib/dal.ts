import "server-only";

import { cache } from "react";
import { redirect } from "next/navigation";
import { decryptSession, readSessionCookie, type SessionPayload } from "@/lib/session";

/** The real (not merely optimistic) authorization boundary — see
 * proxy.ts for the optimistic redirect layer. `cache()`-wrapped so every
 * Server Component/Action/Route Handler in a single request shares one
 * decrypt call rather than repeating it.
 *
 * Deliberately read-only: refreshing the access token means writing a
 * new session cookie, which Next.js only allows from a Server Action,
 * Route Handler, or Proxy — never from a plain Server Component render,
 * which is where most callers of this function live. proxy.ts owns the
 * refresh-and-rewrite so the token is already current by the time this
 * runs; if it's still expired here (e.g. a route outside proxy's
 * matcher), that's treated as logged out rather than attempting a write
 * that would throw. */
export const verifySession = cache(async (): Promise<SessionPayload | null> => {
  const cookieValue = await readSessionCookie();
  if (!cookieValue) return null;

  const payload = await decryptSession(cookieValue);
  if (!payload) return null;
  if (Date.now() >= payload.accessTokenExpiresAt) return null;

  return payload;
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
