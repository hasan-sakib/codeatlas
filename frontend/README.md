# CodeAtlas Frontend

Next.js (App Router) frontend for CodeAtlas — authenticated workspace/repository management, semantic search, and a streaming, cited chat with the RAG agent.

## Stack

- **Next.js 16** (App Router, Turbopack), **React 19**, **TypeScript**.
- **Tailwind CSS v4** + **shadcn/ui** (`base-nova` style, built on `@base-ui/react`).
- **Zustand** for the one piece of client-only global state (streamed chat tokens/citations).
- **jose** for signing the app's own session cookie.
- **Vitest** + **React Testing Library** for unit/component tests, **Playwright** for a full-stack e2e smoke test.

## Prerequisites

- Node 20+, npm.
- The CodeAtlas backend reachable at `BACKEND_URL` (see `backend/README`/`docs/modules/rest_api.md`) — Postgres, Redis, and Qdrant running and migrated; Ollama running with the configured model for chat to work.

## Setup

```bash
npm install
cp .env.example .env.local   # fill in BACKEND_URL and a real SESSION_SECRET
npm run dev
```

`SESSION_SECRET` signs this app's own httpOnly session cookie — generate one with `openssl rand -base64 32`. It is unrelated to the backend's `SECURITY__JWT_SECRET_KEY`.

## Auth architecture — why there's a session cookie AND a bearer token

The backend (`POST /auth/login`) returns an access+refresh token pair in a JSON body — it never sets a cookie. This app is the one that mints an **httpOnly session cookie** wrapping those tokens (`lib/session.ts`), following this Next.js version's own documented pattern for JWT-in-body backends (`node_modules/next/dist/docs/01-app/02-guides/authentication.md`, `backend-for-frontend.md`).

- **`lib/dal.ts`** (`verifySession`/`requireSession`) is the real authorization boundary — every Server Component, Server Action, and Route Handler that touches the backend calls through it. It decrypts the session cookie, and if the access token is expired or within 30s of expiring, transparently rotates it via `POST /auth/refresh` and rewrites the cookie (the backend rotates refresh tokens on every use, so this must happen before the old one is invalidated).
- **`proxy.ts`** (this Next.js version's rename of `middleware.ts`) does a cheap, *optimistic* redirect based on the cookie's mere presence — not its validity. It exists purely to avoid a flash of protected UI; `lib/dal.ts` is what actually enforces access.
- **`app/api/backend/[...path]/route.ts`** is a backend-for-frontend proxy for client-originated requests — the chat SSE stream and the client-side search form. It reads the session cookie server-side, attaches `Authorization: Bearer <token>` itself, and streams the backend's response straight through. The browser never receives the JWT and never makes a cross-origin request, so CORS is a non-issue for these calls.
- Server Components and Server Actions call the backend **directly** (`lib/backend.ts`) since they already run server-side — no need to loop through the BFF proxy route for those.

## State management

Almost everything is server-rendered: workspace/repository/conversation lists and history are fetched in Server Components and mutated via Server Actions (`lib/actions/*.ts`), refreshed with `revalidatePath`/`router.refresh()`. The **only** client-side global state is `lib/stores/streaming-store.ts` (Zustand) — the in-flight SSE token buffer and citations for the message currently streaming, which is inherently transient and can't be server-rendered.

## SSE client

`lib/sse-client.ts` parses `text/event-stream` over `fetch` + `ReadableStream`, not `EventSource` — the chat endpoint is a `POST` with a JSON body, which `EventSource` cannot send (`GET`-only). It buffers across stream reads so an event split across two chunks (a real occurrence, not just a theoretical edge case — verified in `lib/sse-client.test.ts`) still parses correctly.

## Known gap: no live indexing progress

The backend has no indexing-progress SSE endpoint (only repository CRUD exists — the `/jobs/{id}/events` endpoint from the original design doc was never built in any completed backend module). `RepositoryIndexingStatus` therefore **polls** `GET /repositories/{id}` every 3s for its `status` field instead of streaming, stopping once the status reaches `ready`/`failed`.

## Commands

```bash
npm run dev          # start the dev server
npm run build         # production build
npm run lint          # eslint
npx tsc --noEmit       # typecheck
npm test               # vitest (unit/component)
npm run test:watch     # vitest, watch mode
npm run e2e             # Playwright full-stack smoke test — requires a live backend, see below
```

## Running the e2e smoke test

`e2e/smoke.spec.ts` drives a real browser through register → create workspace → register a repository → search → start a conversation → send a chat message → log out, against a **live** backend. It is not part of `npm test`/CI's default gate, mirroring the backend's own `-m integration` split — it needs real infrastructure, not just the repo.

To run it locally: bring up Postgres/Redis/Qdrant (and Ollama with the configured model for the chat step), run backend migrations, start the backend (`uvicorn app.main:create_app --factory`), start this app (`npm run dev`), then `npm run e2e`.
