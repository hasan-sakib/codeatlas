// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";
import { encryptSession, type SessionPayload } from "@/lib/session";

const { cookiesMock } = vi.hoisted(() => ({ cookiesMock: vi.fn() }));
vi.mock("next/headers", () => ({ cookies: cookiesMock }));

function fakeCookieJar(value: string | undefined) {
  return {
    get: (name: string) => (name === "codeatlas_session" && value ? { value } : undefined),
  };
}

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

describe("verifySession", () => {
  beforeEach(() => {
    vi.stubEnv("SESSION_SECRET", "test-secret-at-least-32-bytes-long!!");
    vi.resetModules();
    cookiesMock.mockReset();
  });

  it("returns null when no session cookie is present", async () => {
    cookiesMock.mockResolvedValue(fakeCookieJar(undefined));
    const { verifySession } = await import("@/lib/dal");

    expect(await verifySession()).toBeNull();
  });

  it("returns null for a garbage/undecryptable cookie value", async () => {
    cookiesMock.mockResolvedValue(fakeCookieJar("not-a-real-jwt"));
    const { verifySession } = await import("@/lib/dal");

    expect(await verifySession()).toBeNull();
  });

  it("returns the payload for a still-valid session", async () => {
    const payload = makePayload();
    const token = await encryptSession(payload);
    cookiesMock.mockResolvedValue(fakeCookieJar(token));
    const { verifySession } = await import("@/lib/dal");

    const result = await verifySession();

    expect(result?.userId).toBe("user-1");
    expect(result?.email).toBe("amina@example.com");
  });

  it("returns null once the access token has expired — never attempts to refresh or write", async () => {
    // This is the fix itself: verifySession() runs inside plain Server
    // Component renders, where Next.js forbids writing cookies at all.
    // A prior version tried to refresh-and-rewrite right here, which
    // threw "Cookies can only be modified in a Server Action or Route
    // Handler" on every request once the token aged past its TTL.
    const payload = makePayload({ accessTokenExpiresAt: Date.now() - 1_000 });
    const token = await encryptSession(payload);
    cookiesMock.mockResolvedValue(fakeCookieJar(token));
    const { verifySession } = await import("@/lib/dal");

    expect(await verifySession()).toBeNull();
  });
});
