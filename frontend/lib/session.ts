import "server-only";

import { SignJWT, jwtVerify } from "jose";
import { cookies } from "next/headers";

export const SESSION_COOKIE_NAME = "codeatlas_session";

/** Shared between `createSession` (Server Action/Route Handler writes)
 * and proxy.ts (the only other place allowed to write this cookie —
 * see proxy.ts's own comment for why the refresh-and-rewrite logic
 * lives there and not in the DAL). */
export const SESSION_COOKIE_OPTIONS = {
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax" as const,
  path: "/",
  // 30 days, matching the backend's refresh-token lifetime — a longer
  // cookie is pointless since the refresh token behind it will be
  // rejected by the backend once it expires.
  maxAge: 60 * 60 * 24 * 30,
};

// Signs the session cookie itself (Next.js's own secret) — unrelated to
// the backend's JWT_SECRET_KEY, which the browser/Next.js server never
// see or verify. This cookie's payload just carries the backend's
// opaque access/refresh tokens; Next.js trusts the backend to have
// already validated them on every proxied call.
function getSecretKey(): Uint8Array {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error("SESSION_SECRET environment variable is not set");
  }
  return new TextEncoder().encode(secret);
}

export interface SessionPayload {
  accessToken: string;
  refreshToken: string;
  userId: string;
  email: string;
  /** Epoch milliseconds the access token itself expires at (not the
   * session cookie's own expiry) — lets the DAL decide when to refresh
   * without decoding the backend's JWT. */
  accessTokenExpiresAt: number;
  [key: string]: unknown;
}

export async function encryptSession(payload: SessionPayload): Promise<string> {
  return new SignJWT(payload)
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime("30d")
    .sign(getSecretKey());
}

export async function decryptSession(token: string): Promise<SessionPayload | null> {
  try {
    const { payload } = await jwtVerify(token, getSecretKey(), { algorithms: ["HS256"] });
    return payload as SessionPayload;
  } catch {
    return null;
  }
}

export async function createSession(payload: SessionPayload): Promise<void> {
  const encrypted = await encryptSession(payload);
  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, encrypted, SESSION_COOKIE_OPTIONS);
}

export async function readSessionCookie(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(SESSION_COOKIE_NAME)?.value;
}

export async function deleteSession(): Promise<void> {
  const cookieStore = await cookies();
  cookieStore.delete(SESSION_COOKIE_NAME);
}
