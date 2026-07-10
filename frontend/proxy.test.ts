// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { encryptSession, decryptSession, type SessionPayload } from "@/lib/session";

const { refreshMock } = vi.hoisted(() => ({ refreshMock: vi.fn() }));
vi.mock("@/lib/backend", () => ({
  refresh: refreshMock,
  accessTokenExpiryMs: (accessToken: string) => {
    // Test tokens encode their intended expiry as the token string itself.
    return Number(accessToken.replace("new-access-token-exp-", ""));
  },
}));

function makePayload(overrides: Partial<SessionPayload> = {}): SessionPayload {
  return {
    accessToken: "access-token",
    refreshToken: "refresh-token",
    userId: "user-1",
    email: "amina@example.com",
    accessTokenExpiresAt: Date.now() + 60_000,
    ...overrides,
  };
}

function requestWithCookie(path: string, cookieValue?: string): NextRequest {
  const req = new NextRequest(new URL(path, "http://localhost:3000"));
  if (cookieValue) req.cookies.set("codeatlas_session", cookieValue);
  return req;
}

describe("proxy", () => {
  beforeEach(() => {
    vi.stubEnv("SESSION_SECRET", "test-secret-at-least-32-bytes-long!!");
    vi.resetModules();
    refreshMock.mockReset();
  });

  it("redirects to /login (with next=) when no session cookie exists on a protected path", async () => {
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/workspaces"));

    expect(response.status).toBe(307);
    const location = new URL(response.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("next")).toBe("/workspaces");
  });

  it("passes through to a public path with no session cookie", async () => {
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/login"));

    expect(response.status).not.toBe(307);
  });

  it("passes a still-valid session through untouched, with no cookie rewrite", async () => {
    const token = await encryptSession(makePayload());
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/workspaces", token));

    expect(response.status).not.toBe(307);
    expect(response.cookies.get("codeatlas_session")).toBeUndefined();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("redirects an authenticated visitor away from /login to /workspaces", async () => {
    const token = await encryptSession(makePayload());
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/login", token));

    expect(response.status).toBe(307);
    expect(new URL(response.headers.get("location")!).pathname).toBe("/workspaces");
  });

  it("refreshes an expiring session and writes the rotated cookie onto the response", async () => {
    const newExpiry = Date.now() + 900_000;
    refreshMock.mockResolvedValue({
      access_token: `new-access-token-exp-${newExpiry}`,
      refresh_token: "new-refresh-token",
    });
    const token = await encryptSession(makePayload({ accessTokenExpiresAt: Date.now() + 1_000 }));
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/workspaces", token));

    expect(refreshMock).toHaveBeenCalledWith("refresh-token");
    expect(response.status).not.toBe(307);
    const rotatedCookie = response.cookies.get("codeatlas_session")?.value;
    expect(rotatedCookie).toBeDefined();
    const rotatedPayload = await decryptSession(rotatedCookie!);
    expect(rotatedPayload?.refreshToken).toBe("new-refresh-token");
    expect(rotatedPayload?.accessTokenExpiresAt).toBe(newExpiry);
  });

  it("treats a failed refresh as logged out: clears the cookie and redirects", async () => {
    // This is the case that used to leave a session permanently
    // unrecoverable: the backend had already rotated (revoked) the old
    // refresh token by the time the failure surfaced here, so retrying
    // with the same stale cookie could never succeed either.
    refreshMock.mockRejectedValue(new Error("refresh token revoked"));
    const token = await encryptSession(makePayload({ accessTokenExpiresAt: Date.now() + 1_000 }));
    const { default: proxy } = await import("@/proxy");
    const response = await proxy(requestWithCookie("/workspaces", token));

    expect(response.status).toBe(307);
    expect(new URL(response.headers.get("location")!).pathname).toBe("/login");
    const cleared = response.cookies.get("codeatlas_session");
    expect(cleared === undefined || cleared.value === "").toBe(true);
  });
});
