import { NextRequest, NextResponse } from "next/server";
import { verifySession } from "@/lib/dal";

/** Backend-for-frontend proxy: every client-originated fetch (the chat
 * SSE stream, the client-side search form) hits this same-origin route
 * instead of the FastAPI backend directly. It attaches the Authorization
 * header itself from the httpOnly session cookie, so the access token
 * never reaches browser JS, and the browser never makes a cross-origin
 * request at all (Server Components/Actions call the backend directly
 * instead — see lib/backend.ts — since they run server-side already). */

function backendUrl(): string {
  const url = process.env.BACKEND_URL;
  if (!url) throw new Error("BACKEND_URL environment variable is not set");
  return url;
}

const FORWARDED_RESPONSE_HEADERS = ["content-type", "retry-after", "x-request-id"];

async function proxyToBackend(request: NextRequest, path: string[]): Promise<Response> {
  const session = await verifySession();
  if (!session) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }

  const targetUrl = `${backendUrl()}/api/v1/${path.join("/")}${request.nextUrl.search}`;
  const init: RequestInit = {
    method: request.method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.accessToken}`,
    },
  };
  if (!["GET", "HEAD", "DELETE"].includes(request.method)) {
    init.body = await request.text();
  }

  const backendResponse = await fetch(targetUrl, init);

  if (backendResponse.status === 204) {
    return new Response(null, { status: 204 });
  }

  const headers = new Headers();
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = backendResponse.headers.get(name);
    if (value) headers.set(name, value);
  }

  if ((backendResponse.headers.get("content-type") ?? "").includes("text/event-stream")) {
    headers.set("Cache-Control", "no-cache");
    headers.set("Connection", "keep-alive");
    headers.set("X-Accel-Buffering", "no");
    return new Response(backendResponse.body, { status: backendResponse.status, headers });
  }

  const body = await backendResponse.text();
  return new Response(body, { status: backendResponse.status, headers });
}

interface RouteParams {
  params: Promise<{ path: string[] }>;
}

export async function GET(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function POST(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function PATCH(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const { path } = await params;
  return proxyToBackend(request, path);
}

export async function DELETE(request: NextRequest, { params }: RouteParams): Promise<Response> {
  const { path } = await params;
  return proxyToBackend(request, path);
}
