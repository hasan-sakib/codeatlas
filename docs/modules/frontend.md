# Module 18: Frontend

## Purpose

The Next.js App Router UI: authenticated workspace/repository management with indexing status, semantic search, and a streaming, cited chat with the LangGraph agent — the only human-facing surface in the system; everything built so far has been server-side.

## A pre-implementation surprise: the scaffolded Next.js version warns it isn't the one in training data

`create-next-app@latest` produced Next.js 16.2.10 / React 19.2.4, and its own generated `AGENTS.md` states outright: *"This is NOT the Next.js you know... Read the relevant guide in `node_modules/next/dist/docs/` before writing any code."* Taken seriously rather than assumed away — the bundled docs were read before writing any route/layout/data-fetching code, and two facts changed the plan materially:

1. **`middleware.ts` is renamed `proxy.ts`** (same location, same `NextRequest`/`NextResponse` API, same one-file-per-project constraint) — purely a rename, not a behavior change, but writing `middleware.ts` would have silently done nothing.
2. **`cookies()`/`headers()` are async-only** (`await cookies()`), consistent with 15+ but confirmed still true and no longer offering even the deprecated sync fallback's future.

## Auth architecture — adapted from the design's own stated intent, not invented fresh

The design doc's Module 18 section already called for "reading the JWT from an httpOnly-cookie-aware server action... avoided in client JS for XSS safety" but left the mechanism as a "decide" placeholder. A dedicated API-contract verification pass (Module 17's actual shipped auth router, not the original design doc) confirmed the backend returns `{access_token, refresh_token}` in a JSON body and **never sets a cookie** — no `Set-Cookie` anywhere in `auth.py`. Combined with this Next.js version's own `02-guides/authentication.md` and `backend-for-frontend.md` (which document exactly this JWT-in-body scenario), the resulting design:

- **`lib/session.ts`** — mints and reads an httpOnly session cookie (`jose`-signed, `SignJWT`/`jwtVerify`, HS256, unrelated to the backend's own `SECURITY__JWT_SECRET_KEY`) wrapping `{accessToken, refreshToken, accessTokenExpiresAt}`. This app signs it, not the backend — a deliberate refinement of "proxies the backend's Set-Cookie" (the backend has none to proxy).
- **`lib/dal.ts`** — `verifySession()` (`cache()`-wrapped per request) is the real authorization boundary. Reads the cookie, and if the access token is within 30s of expiring, calls `POST /auth/refresh`, rewrites the cookie with the rotated pair, and returns it — done proactively because the backend rotates refresh tokens on every use, so a stale cookie would present an already-revoked token on the next call. `requireSession()` wraps it with a redirect for protected pages.
- **`proxy.ts`** — an *optimistic* redirect only, checking the cookie's mere presence (not validity) to avoid a flash of protected UI. The docs are explicit this is not a security boundary; `lib/dal.ts` is.
- **`app/api/backend/[...path]/route.ts`** — a backend-for-frontend proxy for the two client-originated call sites (the chat SSE stream, the client-side search form). Reads the session cookie server-side, attaches `Authorization: Bearer` itself, and streams the backend's response through unmodified (detecting `text/event-stream` and forwarding the SSE-specific headers). The browser never sees the JWT and never makes a cross-origin request — CORS becomes irrelevant to the browser's own traffic.
- Server Components/Server Actions (`lib/backend.ts`) call the backend directly, since they already execute server-side.

## API contract verification before writing types

Before writing `lib/types.ts`, a dedicated research pass read the actual shipped backend source (not the original design doc) and found several real drifts worth encoding precisely:
- `GET /workspaces` and `GET /repositories` return a **bare array**, not `Envelope<T>`, despite the documented convention — `GET /conversations`, `GET .../messages`, and `POST /search` do use `Envelope<T>`.
- The SSE `CitationEvent` (`{chunk_id, file_path, start_line, end_line, score}`) is **not** the same shape as `SearchResultItem` (which additionally has `symbol_name`/`source`/`text`) — modeled as two distinct TypeScript interfaces, not one conflated type. `components/chat/citation-card.tsx` accepts the superset of optional fields and renders only what's present.
- Errors arrive in two different shapes: `ProblemDetail` (RFC 7807, from the two global exception handlers) and FastAPI's default `{detail: string}` (from ad-hoc `HTTPException`s raised directly in routers/dependencies/the rate limiter). `lib/api-errors.ts`'s `parseApiError` handles both.
- `ProgressEvent`/`SSEEventName.PROGRESS` exist in the backend's schema but nothing ever emits one — modeled in the type union for forward-compatibility, never expected in practice.

## Known gap: no indexing-progress SSE endpoint

`RepositoryIndexingStatus` polls `GET /repositories/{id}` every 3 seconds rather than streaming — the backend has no `/jobs/{id}/events` endpoint (only repository CRUD was ever built; that endpoint from the original design's API table was never implemented in any completed backend module). Polling stops once `status` reaches `ready`/`failed`. Documented rather than silently worked around.

## SSE client

`lib/sse-client.ts` uses `fetch` + `ReadableStream`, not `EventSource` — the chat endpoint is a `POST` with a JSON body, and `EventSource` only supports `GET`. It buffers across stream reads so an event whose terminating `\n\n` lands in a different chunk than its `data:` line still parses correctly — verified with a test that deliberately splits an event mid-payload across two enqueued chunks, not just asserted from a single complete chunk.

## Real bugs found via empirical browser verification, not just typecheck/lint/build

Per the project's standing discipline, the flow was driven through a real Chromium browser (Playwright) against a real Postgres+Redis+Qdrant+Ollama stack — not just `tsc`/`eslint`/`next build`, all of which passed cleanly before this step and still missed the following:

1. **shadcn's `base-nova` `Button` doesn't support `asChild`** (the Radix `Slot` composition pattern from older shadcn styles) — this style is built on `@base-ui/react`, which uses a `render` prop instead (`render={<Link href="..." />}`). Caught by `tsc`, not the browser.
2. **Composing `Button` with a `render={<Link/>}` element logs a runtime console warning**: Base UI's `Button` defaults `nativeButton={true}` and warns when the rendered element isn't an actual `<button>`. Fixed by passing `nativeButton={false}` at each such call site. This one *only* surfaced in the browser console — neither `tsc` nor `eslint` nor `next build` flagged it.
3. **`next-themes` + SSR hydration mismatch** on `<html>`'s `className`/`style` (the theme script mutates them client-side before hydration, by the library's own design) — fixed with `suppressHydrationWarning` on `<html>`, per `next-themes`' own setup documentation, which wasn't consulted until the warning appeared in the browser.
4. **A genuine backend/infra gap, not a frontend bug**: `/search` returned 500 against a freshly-created Qdrant instance — `Collection code_chunks_active doesn't exist`. Module 10's own docs describe the alias bootstrap as a one-time step invoked from an admin/bootstrap script, never wired into app startup, and no existing backend test exercises a truly fresh Qdrant (every integration test seeds its own collection first). The frontend's own behavior here was correct — it caught the 500 and rendered "Search failed. Please try again." rather than crashing — so nothing was changed on the frontend side; the collection was bootstrapped ad hoc to confirm the search UI's happy path separately, then re-verified showing "No results found" against an empty-but-existing collection.

After all four fixes, a full register → create workspace → register repository → check indexing status → search → start a conversation → send a message → receive a real streamed Ollama response → log out pass produced zero console errors.

## Testing notes

- **Unit** (`lib/sse-client.test.ts`): single-chunk event, an event's `\n\n` terminator split across two chunks, multiple events in one chunk, a data-only block with no `event:` line (skipped), and a non-ok response throwing.
- **Unit** (`lib/stores/streaming-store.test.ts`): every Zustand action in isolation, including that `startStreaming` clears prior state and `reset` returns to initial values.
- **Unit** (`lib/api-errors.test.ts`): both real backend error shapes (`ProblemDetail` and FastAPI's default `{detail}`), a non-JSON body falling back to `statusText`, and `x-request-id` header fallback when the body has no `correlation_id`.
- **Component** (`components/chat/citation-card.test.tsx`): renders the `CitationEvent`-only field set correctly, and separately the full `SearchResultItem` superset (symbol/source badges, code preview) — asserting the two shapes are genuinely handled independently, not conflated.
- **Component** (`components/workspace/repository-indexing-status.test.tsx`): no polling when already terminal; polls via fake timers through `pending → indexing → ready`, hitting the exact BFF proxy URL; stops polling once terminal; survives a transient fetch rejection without crashing.
- **Component** (`components/chat/chat-panel.test.tsx`): renders finalized history from props; a deterministic mid-stream assertion (via a manually-gated async generator, not a race against an instantly-resolving mock) that the optimistic user bubble and partial assistant text are both visible before the stream completes, then that `router.refresh()` fires and streaming state resets after; a toast fires and state still resets cleanly if the stream throws; the Send button stays disabled for an empty message.
- **E2E** (`e2e/smoke.spec.ts`, Playwright): the same register → workspace → repository → search → chat → logout flow, run against a live backend — verified passing manually during development (see the bugs above) but not part of the default `npm test` gate, mirroring the backend's own `-m integration` split since it needs real infrastructure the harness doesn't provide.
- `npx tsc --noEmit`: clean. `npx eslint .`: clean. `npm run build`: succeeds (Turbopack). `npm test`: 25 passed (6 files). `npm run e2e`: 1 passed, run manually against a live Postgres/Redis/Qdrant/Ollama stack.
