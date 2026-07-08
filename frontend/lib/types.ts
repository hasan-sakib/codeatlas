// Mirrors the backend's actual shipped shapes (verified against
// backend/app/api/schemas/*.py and backend/app/api/streaming/events.py —
// not the original design doc, which drifted from real implementation in
// a few places, e.g. GET /workspaces and GET /repositories return a bare
// array, not an Envelope, despite the documented convention).

export interface Envelope<T> {
  data: T;
  meta: Record<string, unknown>;
}

/** RFC 7807 error body — emitted only by the backend's two global
 * exception handlers (domain errors, unhandled exceptions). Ad-hoc
 * `HTTPException`s raised directly in a router/dependency instead
 * produce FastAPI's default `{ detail: string }` shape — see
 * `parseApiError` in api-errors.ts, which handles both. */
export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail?: string | null;
  instance?: string | null;
  correlation_id?: string | null;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  email: string;
  full_name: string | null;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

// ---------------------------------------------------------------------------
// Workspaces
// ---------------------------------------------------------------------------

export interface Workspace {
  id: string;
  owner_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Repositories
// ---------------------------------------------------------------------------

export type RepositorySourceType = "git_url" | "upload_zip";
export type RepositoryStatus = "pending" | "indexing" | "ready" | "failed";

export interface Repository {
  id: string;
  workspace_id: string;
  source_type: RepositorySourceType;
  git_url: string | null;
  default_branch: string | null;
  local_path: string | null;
  last_indexed_commit_sha: string | null;
  status: RepositoryStatus;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResultItem {
  chunk_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  symbol_name: string | null;
  score: number;
  source: string;
  text: string | null;
}

// ---------------------------------------------------------------------------
// Conversations
// ---------------------------------------------------------------------------

export type MessageRole = "user" | "assistant" | "system" | "tool";

/** The shape a citation takes once persisted on a Message — distinct from
 * SSE's CitationEvent (below) only in that it's already attached to a
 * message rather than streamed standalone; both omit symbol_name/source,
 * unlike SearchResultItem. */
export interface Citation {
  chunk_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  score: number;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  user_id: string;
  title: string | null;
  summary: string | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  citations: Citation[];
  token_count: number;
  created_at: string | null;
}

// ---------------------------------------------------------------------------
// SSE event contract (backend/app/api/streaming/events.py, verified)
// ---------------------------------------------------------------------------

export type SSEEventName = "token" | "citation" | "progress" | "done" | "error";

export interface TokenEventPayload {
  text: string;
}

/** Deliberately NOT the same shape as SearchResultItem — the backend's
 * CitationEvent has no symbol_name/source field. */
export interface CitationEventPayload {
  chunk_id: string;
  file_path: string;
  start_line: number;
  end_line: number;
  score: number;
}

export interface ProgressEventPayload {
  stage: string;
  percent: number | null;
  message: string | null;
}

export interface DoneEventPayload {
  message_id: string | null;
}

export interface ErrorEventPayload {
  type: string;
  title: string;
  detail: string | null;
}

export interface SSEEvent {
  name: SSEEventName;
  data:
    | TokenEventPayload
    | CitationEventPayload
    | ProgressEventPayload
    | DoneEventPayload
    | ErrorEventPayload;
}

// ---------------------------------------------------------------------------
// Docs generation
// ---------------------------------------------------------------------------

export type DocGenerationScope = "file" | "module" | "repository";

export interface GenerateDocsResult {
  scope: DocGenerationScope;
  path: string | null;
  markdown: string;
}
