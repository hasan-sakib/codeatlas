import { NextRequest, NextResponse } from "next/server";
import {
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_OPTIONS,
  decryptSession,
  encryptSession,
  type SessionPayload,
} from "@/lib/session";
import { refresh as refreshBackend, accessTokenExpiryMs } from "@/lib/backend";

const PUBLIC_PATHS = new Set(["/login", "/register"]);
const REFRESH_SKEW_MS = 30_000;

/** Owns the actual session-refresh-and-cookie-write logic — not
 * lib/dal.ts's `verifySession()`, which only reads. Next.js only allows
 * writing cookies from a Server Action, Route Handler, or Proxy; it
 * does NOT allow it during a plain Server Component render. Every
 * protected page render calls `verifySession()`, so a refresh-and-write
 * living there would throw "Cookies can only be modified in a Server
 * Action or Route Handler" the moment a session's access token aged
 * past its 15-minute TTL — verified directly, and worse than just an
 * error: the backend rotates (and revokes) the old refresh token the
 * instant `refreshBackend()` succeeds, so a write that then fails to
 * persist leaves the session permanently unrecoverable. Proxy runs
 * before every matched request and is one of the few places allowed to
 * write response cookies unconditionally, so the refresh happens here,
 * once, before any Server Component ever sees the request. */
export default async function proxy(request: NextRequest): Promise<NextResponse> {
  const { pathname } = request.nextUrl;
  const isPublicPath = PUBLIC_PATHS.has(pathname);
  const cookieValue = request.cookies.get(SESSION_COOKIE_NAME)?.value;

  let session: SessionPayload | null = null;
  let refreshedCookieValue: string | null = null;

  if (cookieValue) {
    session = await decryptSession(cookieValue);
    if (session && Date.now() >= session.accessTokenExpiresAt - REFRESH_SKEW_MS) {
      try {
        const tokens = await refreshBackend(session.refreshToken);
        const rotated: SessionPayload = {
          ...session,
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          accessTokenExpiresAt: accessTokenExpiryMs(tokens.access_token),
        };
        refreshedCookieValue = await encryptSession(rotated);
        session = rotated;
      } catch {
        // Refresh token already expired/revoked — nothing to recover;
        // treat as logged out below and let the redirect/response path
        // clear the stale cookie.
        session = null;
      }
    }
  }

  const isAuthenticated = session !== null;

  if (!isAuthenticated && !isPublicPath && pathname !== "/") {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    const response = NextResponse.redirect(loginUrl);
    if (cookieValue) response.cookies.delete(SESSION_COOKIE_NAME);
    return response;
  }

  if (isAuthenticated && isPublicPath) {
    return NextResponse.redirect(new URL("/workspaces", request.url));
  }

  // Rewrite the incoming request's own cookie so any Server Component/
  // Action downstream in *this* request sees the refreshed token too,
  // not just the browser on its next request.
  if (refreshedCookieValue) {
    request.cookies.set(SESSION_COOKIE_NAME, refreshedCookieValue);
  }
  const response = NextResponse.next({ request });
  if (refreshedCookieValue) {
    response.cookies.set(SESSION_COOKIE_NAME, refreshedCookieValue, SESSION_COOKIE_OPTIONS);
  } else if (cookieValue && !isAuthenticated) {
    response.cookies.delete(SESSION_COOKIE_NAME);
  }
  return response;
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
