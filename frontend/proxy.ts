import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE_NAME } from "@/lib/session";

const PUBLIC_PATHS = new Set(["/login", "/register"]);

/** Optimistic redirect only — checks the session cookie's mere presence,
 * not its validity (Proxy can't run the DAL's decrypt+refresh logic
 * cheaply on every request). The real authorization boundary is
 * `verifySession()`/`requireSession()` in lib/dal.ts, called by every
 * protected Server Component, Server Action, and Route Handler; a
 * forged or expired cookie that slips past this check is still rejected
 * there. This exists purely so an unauthenticated visitor doesn't see a
 * flash of protected UI before a server-side redirect. */
export default function proxy(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl;
  const hasSessionCookie = Boolean(request.cookies.get(SESSION_COOKIE_NAME)?.value);
  const isPublicPath = PUBLIC_PATHS.has(pathname);

  if (!hasSessionCookie && !isPublicPath && pathname !== "/") {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (hasSessionCookie && isPublicPath) {
    return NextResponse.redirect(new URL("/workspaces", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
