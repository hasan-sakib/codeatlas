import type { ProblemDetail } from "@/lib/types";

/** Unifies the backend's two distinct error shapes: `ProblemDetail`
 * (RFC 7807, from the two global exception handlers) and FastAPI's
 * default `{ detail: string }` (from ad-hoc `HTTPException`s raised
 * directly in routers/dependencies/the rate limiter). Verified both
 * shapes occur in the real backend — see docs/modules/rest_api.md. */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly correlationId: string | null;

  constructor(status: number, title: string, detail: string | null, correlationId: string | null) {
    super(detail ?? title);
    this.name = "ApiError";
    this.status = status;
    this.title = title;
    this.correlationId = correlationId;
  }
}

export async function parseApiError(response: Response): Promise<ApiError> {
  const correlationId = response.headers.get("x-request-id");
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ApiError(response.status, response.statusText, null, correlationId);
  }

  if (isProblemDetail(body)) {
    return new ApiError(body.status, body.title, body.detail ?? null, body.correlation_id ?? correlationId);
  }
  if (isFastApiDefaultError(body)) {
    return new ApiError(response.status, response.statusText, body.detail, correlationId);
  }
  return new ApiError(response.status, response.statusText, null, correlationId);
}

function isProblemDetail(body: unknown): body is ProblemDetail {
  return (
    typeof body === "object" &&
    body !== null &&
    "title" in body &&
    "status" in body &&
    typeof (body as { title: unknown }).title === "string"
  );
}

function isFastApiDefaultError(body: unknown): body is { detail: string } {
  return (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string"
  );
}
