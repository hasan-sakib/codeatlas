import "server-only";

import { decodeJwt } from "jose";
import type { TokenPair, User } from "@/lib/types";
import { ApiError, parseApiError } from "@/lib/api-errors";

function backendUrl(): string {
  const url = process.env.BACKEND_URL;
  if (!url) {
    throw new Error("BACKEND_URL environment variable is not set");
  }
  return url;
}

/** Unauthenticated call straight to FastAPI — used only by the three
 * auth endpoints that don't require a bearer token. */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${backendUrl()}/api/v1${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
}

export async function register(email: string, password: string, fullName?: string): Promise<User> {
  const res = await backendFetch("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name: fullName || null }),
  });
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<User>;
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await backendFetch("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<TokenPair>;
}

export async function refresh(refreshToken: string): Promise<TokenPair> {
  const res = await backendFetch("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<TokenPair>;
}

export async function logout(accessToken: string, refreshToken: string): Promise<void> {
  const res = await backendFetch("/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!res.ok && res.status !== 401) throw await parseApiError(res);
}

export async function fetchCurrentUser(accessToken: string): Promise<User> {
  const res = await backendFetch("/auth/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<User>;
}

/** Decode-only (no signature verification) read of the access token's
 * `exp` claim, used purely to schedule a proactive refresh. The backend
 * remains the sole authority on whether a token is actually valid —
 * every real call still gets rejected with 401 if this is wrong. */
export function accessTokenExpiryMs(accessToken: string): number {
  const claims = decodeJwt(accessToken);
  if (!claims.exp) throw new Error("access token has no exp claim");
  return claims.exp * 1000;
}

/** Authenticated call straight to FastAPI — used by Server Components
 * and Server Actions, which run server-side and can talk to the backend
 * directly without going through the browser-facing BFF proxy route. */
export async function authedBackendFetch(
  path: string,
  accessToken: string,
  init?: RequestInit,
): Promise<Response> {
  return fetch(`${backendUrl()}/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...init?.headers,
    },
    cache: "no-store",
  });
}

export async function authedJson<T>(path: string, accessToken: string, init?: RequestInit): Promise<T> {
  const res = await authedBackendFetch(path, accessToken, init);
  if (!res.ok) throw await parseApiError(res);
  return res.json() as Promise<T>;
}

export { ApiError };
