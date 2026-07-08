import { describe, expect, it } from "vitest";
import { ApiError, parseApiError } from "@/lib/api-errors";

function fakeResponse(body: unknown, opts: { status?: number; statusText?: string; headers?: Record<string, string> } = {}): Response {
  return {
    status: opts.status ?? 500,
    statusText: opts.statusText ?? "Internal Server Error",
    headers: new Headers(opts.headers ?? {}),
    json: async () => body,
  } as unknown as Response;
}

describe("parseApiError", () => {
  it("parses a ProblemDetail body (global exception handler shape)", async () => {
    const response = fakeResponse(
      {
        type: "https://codeatlas.dev/errors/404",
        title: "Not Found",
        status: 404,
        detail: "Workspace not found",
        correlation_id: "abc-123",
      },
      { status: 404 },
    );

    const error = await parseApiError(response);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.title).toBe("Not Found");
    expect(error.message).toBe("Workspace not found");
    expect(error.correlationId).toBe("abc-123");
  });

  it("parses FastAPI's default { detail } shape (ad-hoc HTTPException)", async () => {
    const response = fakeResponse({ detail: "Invalid git URL" }, { status: 400, statusText: "Bad Request" });

    const error = await parseApiError(response);

    expect(error.status).toBe(400);
    expect(error.title).toBe("Bad Request");
    expect(error.message).toBe("Invalid git URL");
  });

  it("falls back to statusText when the body is not JSON", async () => {
    const response = {
      status: 502,
      statusText: "Bad Gateway",
      headers: new Headers(),
      json: async () => {
        throw new SyntaxError("Unexpected token");
      },
    } as unknown as Response;

    const error = await parseApiError(response);

    expect(error.status).toBe(502);
    expect(error.message).toBe("Bad Gateway");
  });

  it("prefers the x-request-id header when the body has no correlation_id", async () => {
    const response = fakeResponse(
      { detail: "boom" },
      { status: 500, headers: { "x-request-id": "header-correlation-id" } },
    );

    const error = await parseApiError(response);

    expect(error.correlationId).toBe("header-correlation-id");
  });
});
